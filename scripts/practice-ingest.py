#!/usr/bin/env python3
"""English practice ingest — transcription + fluency metrics for recorded practice.

Run with the project venv (NOT the stock python3 — see scripts/practice-setup.sh):

    .venv-practice/bin/python scripts/practice-ingest.py [--commit] [--source DIR] [--out DIR]

Sources scanned, newest first:
  ~/EnglishPractice/                                  every audio file
  Voice Memos iCloud container (when sync enabled)    files named eng*
  iCloud Drive/EnglishPractice (when it exists)       files named eng*

Idempotent: content-hashed state in logs/practice/.ingested.json. Each new
recording produces logs/practice/<date>-<slug>.json (+ .txt transcript):
whisper transcript with per-word confidence, wpm, fillers, pause/rate metrics
from the vendored de Jong & Wempe syllable-nuclei script, pitch stats, and
low-confidence pronunciation suspects. If AZURE_SPEECH_KEY and
AZURE_SPEECH_REGION are set, each recording also gets the dual-locale Azure
pronunciation assessment (see scripts/azure_pa.py) — that step uploads audio
to Azure; everything else is local.

Telemetry here is FORMATIVE coaching signal. Nothing feeds tracking.tsv.
"""
import argparse, hashlib, json, math, re, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRAAT_SCRIPT = REPO / "scripts" / "syllable-nuclei-v2.praat"
OUT_DEFAULT = REPO / "logs" / "practice"
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aiff", ".aif", ".flac", ".ogg", ".webm"}
FILLERS = {"um", "uh", "erm", "er", "ah", "eh", "hmm", "mm", "mmm"}
LOW_CONF = 0.50

def sources():
    home = Path.home()
    return [
        (home / "EnglishPractice", False),
        (home / "Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings", True),
        (home / "Library/Mobile Documents/com~apple~CloudDocs/EnglishPractice", True),
    ]

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def to_wav(src, dst):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", str(dst)],
        check=True)

def transcribe(wav):
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(wav), language="en", beam_size=5, vad_filter=True, word_timestamps=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append({"w": w.word.strip(), "start": round(w.start, 2),
                          "end": round(w.end, 2), "p": round(w.probability, 3)})
    return words, info.duration

def praat_metrics(wav):
    import parselmouth
    from parselmouth.praat import run_file
    out = run_file(str(PRAAT_SCRIPT), -25.0, 2.0, 0.3, 0.1, False,
                   str(wav.parent) + "/", wav.name, capture_output=True)[1]
    body = out[out.index("{"): out.rindex("}") + 1]
    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        raw = dict(re.findall(r'"([^"]+)":\s*"([^"]*)"', body))
    num = lambda k: float(raw[k]) if k in raw and raw[k] not in ("", "--undefined--") else None
    metrics = {
        "syllables": num("syllableCount"),
        "pauses": num("pauseCount"),
        "duration_s": num("totalDuration"),
        "phonation_s": num("speakingTotalDuration"),
        "speech_rate_syll_s": num("speakingRate"),
        "articulation_rate_syll_s": num("articulationRate"),
        "avg_syllable_s": num("averageSylableDuration"),
    }
    snd = parselmouth.Sound(str(wav))
    pitch = snd.to_pitch()
    f0 = pitch.selected_array["frequency"]
    voiced = sorted(v for v in f0 if v > 0)
    if len(voiced) >= 10:
        q = lambda p: voiced[min(len(voiced) - 1, int(p * len(voiced)))]
        metrics["f0_median_hz"] = round(q(0.5), 1)
        metrics["f0_range_semitones"] = round(12 * math.log2(q(0.9) / q(0.1)), 1)
    return metrics

def norm_word(w):
    return re.sub(r"[^a-z']", "", w.lower())

def analyse(words, duration):
    toks = [norm_word(w["w"]) for w in words]
    filler_n = sum(1 for t in toks if t in FILLERS)
    content_n = len(toks) - filler_n
    suspects = [
        {"word": norm_word(w["w"]), "p": w["p"], "at_s": w["start"]}
        for w in words
        if w["p"] < LOW_CONF and len(norm_word(w["w"])) >= 4
        and norm_word(w["w"]) not in FILLERS
    ][:20]
    return {
        "words": len(toks),
        "fillers": filler_n,
        "wpm": round(content_n / duration * 60, 1) if duration else None,
        "pronunciation_suspects": suspects,
    }

def ingest_one(path, out_dir, azure):
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "rec.wav"
        to_wav(path, wav)
        words, duration = transcribe(wav)
        record = {
            "source": path.name,
            "recorded": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "ingested": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_s": round(duration, 1),
            **analyse(words, duration),
            "praat": praat_metrics(wav),
            "word_confidences": words,
            "azure": None,
        }
        if azure:
            try:
                from azure_pa import dual_locale_assessment
                record["azure"] = dual_locale_assessment(wav)
            except Exception as e:
                record["azure"] = {"error": str(e)}
    date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-") or "rec"
    base = out_dir / f"{date}-{slug}"
    i, final = 0, base
    while (final.with_suffix(".json")).exists():
        i += 1
        final = Path(f"{base}-{i}")
    transcript = " ".join(w["w"] for w in words)
    final.with_suffix(".json").write_text(
        json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    final.with_suffix(".txt").write_text(transcript + "\n", encoding="utf-8")
    return final.with_suffix(".json"), record

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="git add+commit+push new practice logs")
    ap.add_argument("--source", type=Path, help="extra/override source dir (everything ingested)")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()
    sys.path.insert(0, str(REPO / "scripts"))

    args.out.mkdir(parents=True, exist_ok=True)
    state_path = args.out / ".ingested.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

    import os
    azure = bool(os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"))

    src = sources()
    if args.source:
        src = [(args.source, False)] + src
    candidates = []
    for folder, need_prefix in src:
        if not folder.is_dir():
            continue
        for p in folder.iterdir():
            if p.suffix.lower() in AUDIO_EXT and (not need_prefix or p.name.lower().startswith("eng")):
                candidates.append(p)
    candidates.sort(key=lambda p: p.stat().st_mtime)

    new = []
    for p in candidates:
        digest = sha256(p)
        if digest in state:
            continue
        print(f"ingesting {p.name} ...", flush=True)
        out_file, record = ingest_one(p, args.out, azure)
        state[digest] = {"file": p.name, "output": out_file.name, "at": record["ingested"]}
        tmp = state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
        tmp.replace(state_path)
        new.append((p.name, out_file, record))
        print(f"  -> {out_file.name}: {record['words']} words, "
              f"{record['wpm']} wpm, {record['fillers']} fillers, "
              f"{len(record['pronunciation_suspects'])} suspects"
              + (", azure ok" if azure and record["azure"] and "error" not in (record["azure"] or {}) else ""))

    if not new:
        print("nothing new to ingest")
        return
    if args.commit:
        subprocess.run(["git", "-C", str(REPO), "add", str(args.out)], check=True)
        subprocess.run(["git", "-C", str(REPO), "commit", "-m",
                        f"observations: practice ingest ({len(new)} recording{'s' if len(new) != 1 else ''})\n\n"
                        "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"], check=True)
        subprocess.run(["git", "-C", str(REPO), "push"], check=True)

if __name__ == "__main__":
    main()
