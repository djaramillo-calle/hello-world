#!/usr/bin/env python3
"""English practice ingest — transcription + fluency metrics for recorded practice.

Run with the project venv (NOT the stock python3 — see scripts/practice-setup.sh):

    .venv-practice/bin/python scripts/practice-ingest.py [--commit] [--source DIR] [--out DIR]

Sources scanned (files ingested oldest first, so outputs stay chronological):
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
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aiff", ".aif", ".flac", ".ogg", ".webm",
             ".mp4", ".mkv", ".opus", ".amr", ".3gp"}  # video containers: audio track extracted via ffmpeg
FILLERS = {"um", "uh", "erm", "er", "ah", "eh", "hmm", "mm", "mmm"}
LOW_CONF = 0.50

def sources():
    home = Path.home()
    fixed = [
        (home / "EnglishPractice", False),
        (home / "Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings", True),
        (home / "Library/Mobile Documents/com~apple~CloudDocs/EnglishPractice", True),
    ]
    # Google Drive desktop mounts (any signed-in account): a dedicated
    # EnglishPractice folder in My Drive is ingested wholesale
    for mount in (home / "Library/CloudStorage").glob("GoogleDrive-*"):
        fixed.append((mount / "My Drive" / "EnglishPractice", False))
        # ASR (com.nll.asr, the Android recorder) uploads into its own tree:
        # My Drive/com.nll.asr/EnglishPractice/Recordings/<device>/<yyyy>/<mm>/<dd>/<file>.m4a — scanned recursively
        fixed.append((mount / "My Drive" / "com.nll.asr" / "EnglishPractice", False))
    return fixed

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

def recording_kind(name):
    """'eng read A03.m4a' → ('read', 'A03'); 'eng ai' → ('ai', None); anything else → ('free', None)."""
    s = re.sub(r"\.[a-z0-9]+$", "", name.lower()).replace("_", " ").replace("-", " ")
    m = re.search(r"\bread\b\s*([a-z]\d{2})?", s)
    if m:
        return "read", (m.group(1) or "").upper() or None
    for k in ("432", "ai", "debrief", "warmup", "drill", "tutor"):
        if re.search(r"\b%s\b" % k, s):
            return k, None
    return "free", None

MIN_PASSAGE_OVERLAP = 0.5   # same threshold as practice-review's guard

def library_chunks():
    """Book passages from library/*.json (built by scripts/passage-import.py; gitignored, copyrighted)."""
    out = []
    for f in sorted((REPO / "library").glob("*.json")) if (REPO / "library").is_dir() else []:
        try:
            for c in json.loads(f.read_text(encoding="utf-8")).get("chunks") or []:
                if c.get("id") and c.get("text"): out.append({"id": c["id"], "text": c["text"], "title": c.get("chapter", "")})
        except (OSError, ValueError):
            continue
    return out

def detect_passage(transcript, passages=None):
    """Which passage (if any) this transcript is a reading of: the id whose words the transcript
    covers best, when it covers at least MIN_PASSAGE_OVERLAP of them. Lets an un-named ASR file
    still be scored as a read-aloud, and corrects a wrong id in the name."""
    if passages is None:
        try:
            passages = json.loads((REPO / "passages" / "passages.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None, 0.0
    tw = set(re.findall(r"[a-z']+", (transcript or "").lower()))
    if not tw:
        return None, 0.0
    cands = [passages.get("anchor") or {}] + list(passages.get("passages") or []) + (library_chunks() if passages.get("_with_library", True) else [])
    best, score = None, 0.0
    for c in cands:
        rw = set(re.findall(r"[a-z']+", str(c.get("text", "")).lower()))
        if not rw: continue
        ov = len(tw & rw) / len(rw)
        if ov > score: best, score = c.get("id"), ov
    return (best, round(score, 2)) if score >= MIN_PASSAGE_OVERLAP else (None, round(score, 2))

def passage_text(pid):
    """Reference text for a read-aloud, from passages/passages.json (None when unknown)."""
    if not pid:
        return None
    try:
        P = json.loads((REPO / "passages" / "passages.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for c in library_chunks():
        if c["id"] == pid: return c["text"]
    if P.get("anchor", {}).get("id") == pid:
        return P["anchor"]["text"]
    return next((p["text"] for p in P.get("passages", []) if p.get("id") == pid), None)

def ingest_one(path, out_dir, azure):
    kind, pid = recording_kind(path.name)
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "rec.wav"
        to_wav(path, wav)
        words, duration = transcribe(wav)
        # The transcript decides the passage: an un-named file that reads A00 is scored as A00, and a
        # name that says A00 while the words are R03's is corrected. Conversations never match a passage.
        detected, overlap = detect_passage(" ".join(w["w"] for w in words))
        note = None
        if detected and detected != pid:
            note = f"passage {detected} detected from the transcript ({overlap:.0%} overlap)" + (f"; name said {pid}" if pid else "; file was not named")
            kind, pid = "read", detected
        elif kind == "read" and pid and not detected:
            note = f"name says {pid} but the transcript covers only {overlap:.0%} of it — scored unscripted"
        reference = passage_text(pid) if (kind == "read" and detected) else None
        record = {
            "source": path.name,
            "recorded": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "ingested": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_s": round(duration, 1),
            "kind": kind,
            "passage": pid,
            "scripted": bool(reference),
            "passage_overlap": overlap,
            "kind_note": note,
            **analyse(words, duration),
            "praat": praat_metrics(wav),
            "word_confidences": words,
            "azure": None,
        }
        if azure:
            try:
                from azure_pa import dual_locale_assessment
                record["azure"] = dual_locale_assessment(wav, reference_text=reference)
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

def save_state(state_path, state):
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    tmp.replace(state_path)

def selftest():
    P = {"anchor": {"id": "A00", "text": "Every Thursday I go to the gym after work and then I cook dinner."},
         "passages": [{"id": "R01", "text": "The station was busy this morning and the train was late again."}], "_with_library": False}
    assert detect_passage("every thursday i go to the gym after work and then i cook dinner", P) == ("A00", 1.0)
    assert detect_passage("the station was busy this morning, the train late again", P)[0] == "R01"
    assert detect_passage("two world wars in one generation separated by a chain of local wars", P)[0] is None
    assert detect_passage("", P) == (None, 0.0)
    assert recording_kind("eng read A00 - 2026_09_09.m4a") == ("read", "A00")
    assert recording_kind("1788988987643 - 2026_09_09_22_19_23.m4a") == ("free", None)
    assert recording_kind("eng ai.m4a") == ("ai", None)
    print("practice-ingest.py selftest: OK")

def main():
    if "--selftest" in sys.argv:
        return selftest()
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
        for p in folder.rglob("*"):   # subfolders too: the phone uploads into EnglishPractice/Recordings
            if not p.is_file() or any(part.startswith(".") for part in p.relative_to(folder).parts):
                continue
            if p.suffix.lower() in AUDIO_EXT and (not need_prefix or p.name.lower().startswith("eng")):
                candidates.append(p)
    candidates.sort(key=lambda p: p.stat().st_mtime)

    new = []
    for p in candidates:
        digest = sha256(p)
        if digest in state:
            continue
        print(f"ingesting {p.name} ...", flush=True)
        try:
            if p.stat().st_size == 0:
                raise ValueError("empty file (still syncing?)")
            out_file, record = ingest_one(p, args.out, azure)
        except Exception as e:   # one bad file must never block newer recordings (oldest-first + state-on-success would re-crash forever)
            state[digest] = {"file": p.name, "error": f"{type(e).__name__}: {str(e)[:200]}",
                             "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            save_state(state_path, state)
            print(f"  !! skipped {p.name}: {state[digest]['error']} (quarantined by content hash; a re-synced file has a new hash)", flush=True)
            continue
        state[digest] = {"file": p.name, "output": out_file.name, "at": record["ingested"]}
        save_state(state_path, state)
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
