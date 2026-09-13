#!/usr/bin/env python3
"""Say it — the production half of the pronunciation loop.

    python3 scripts/sayit.py --build            # ledger → logs/sayit/words.json + model clips (Azure TTS)
    .venv-practice/bin/python scripts/sayit.py --score --dir <folder>   # the phone's attempts → results.json
    python3 scripts/sayit.py --selftest

The reads flag words; this turns the repeat offenders into something he can practise and be scored on.
The unit is always the word IN THE SENTENCE it was flagged in: his failures are connected-speech
failures (unstressed syllables collapsing, final consonants dropping) and an isolated word is a
different motor task. The Azure key never reaches the phone — the app plays a pre-rendered clip,
records the attempt and writes it to the synced folder; the scoring happens here.

Files (inside the app's folder, Drive EnglishPractice/pairs, docs/CONTRACT.md in the app repo):
  sayit.zip                   coach → app: ONE file holding words.json, results.json and clips/<id>.ogg
                              (an en-GB neural voice reading each `sentence`). One file because the Drive
                              service account has no storage quota and can only PATCH files that already
                              exist — the owner created an empty sayit.zip once, and it is updated in place
                              forever after. The app unpacks it; it never writes it.
  sayit/attempts/<ts>_<id>.*  app → coach: his recording + a sidecar naming the sentence

Status: active → retired after RETIRE_HITS attempts at accuracy ≥ RETIRE_AT; → tutor when it is
still active after TUTOR_WEEKS (a motor problem a human should hear, not more self-practice).
Formative only: nothing here reaches tracking.tsv.
"""
import argparse, datetime as dt, json, os, pathlib, re, subprocess, sys, tempfile, urllib.request, zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "logs" / "sayit"
LEDGER = REPO / "logs" / "pronunciation-ledger.json"
PRACTICE = REPO / "logs" / "practice"
VOICE = "en-GB-RyanNeural"
MAX_ACTIVE = 12          # what the app may hold; it shows per_session of them a day
PER_SESSION = 5
MIN_FLAGGED = 2          # a word must have been flagged on this many recordings (same bar as the cards)
MIN_RATE = 0.25          # ...AND flagged on at least this share of the times it was actually read. A count
                         # alone promotes function words: "the" flagged 3x across 200 occurrences is noise,
                         # while "imperialist" flagged 3x out of 4 is broken. Rate separates them.
RETIRE_AT, RETIRE_HITS = 80.0, 2
TUTOR_WEEKS = 3

def load_json(p, default):
    try: return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError): return default

def dump_json(p, obj):
    p = pathlib.Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]

def carrier(word, texts, min_words=5, max_words=28):
    """The shortest usable sentence from the passages that actually contains the word.
    Short enough to say in one breath, long enough to carry connected speech."""
    rx = re.compile(r"\b" + re.escape(word) + r"\b", re.I)
    cands = [s for t in texts for s in sentences(t) if rx.search(s) and min_words <= len(s.split()) <= max_words]
    return min(cands, key=lambda s: len(s.split())) if cands else None

def occurrences(word, texts):
    rx = re.compile(r"\b" + re.escape(word) + r"\b", re.I)
    return sum(len(rx.findall(t)) for t in texts)

def passage_texts(practice_dir=PRACTICE):
    """Every passage text a review referred to, newest review first — where the flagged words live."""
    pi = _load("practice-ingest")
    out, seen = [], set()
    revs = sorted(pathlib.Path(practice_dir).glob("*.review.json"), reverse=True) if pathlib.Path(practice_dir).is_dir() else []
    for f in revs:
        pid = (load_json(f, {}) or {}).get("passage")
        if not pid or pid in seen: continue
        seen.add(pid)
        t = pi.passage_text(pid)
        if t: out.append(t)
    return out

def _load(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def pick(ledger, results, texts, max_active=MAX_ACTIVE, min_flagged=MIN_FLAGGED, min_rate=MIN_RATE, today=None):
    """Words he actually gets wrong, worst rate first, each with a sentence he has read.
    Ranked by how OFTEN he misses the word, not by how often it appears."""
    today = today or dt.date.today().isoformat()
    cand = []
    for w, W in (ledger.get("words") or {}).items():
        n = W.get("count", 0)
        if n < min_flagged: continue
        st = ((results.get("words") or {}).get(w) or {}).get("status")
        if st in ("retired", "tutor"): continue
        seen = occurrences(w, texts)
        rate = n / seen if seen else 1.0
        if rate < min_rate: continue             # a word read 200 times and missed 3 is not the problem
        s = carrier(w, texts)
        if not s: continue                       # never invent a sentence he did not read
        cls = [c for c, L in (ledger.get("phonemes") or {}).items() if w in (L.get("words") or {})]
        cand.append((round(rate, 3), n, {"id": w, "word": w, "sentence": s, "clip": f"clips/{w}.ogg", "ipa": "",
                                         "classes": sorted(cls), "flagged_on": n, "read_on": seen,
                                         "miss_rate": round(rate, 2), "added": today}))
    cand.sort(key=lambda t: (-t[0], -t[1], t[2]["id"]))
    return [c[2] for c in cand[:max_active]]

def tts(text, dest, voice=VOICE, key=None, region=None):
    """Azure neural text-to-speech → Ogg/Opus. Key stays here; the phone only ever sees the bytes."""
    key = key or os.environ.get("AZURE_SPEECH_KEY"); region = region or os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region: return False
    ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-GB">'
            f'<voice name="{voice}"><prosody rate="-8%">{_xml(text)}</prosody></voice></speak>')
    req = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1", data=ssml.encode("utf-8"),
        headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": "ogg-48khz-16bit-mono-opus", "User-Agent": "english-runbook"})
    with urllib.request.urlopen(req, timeout=60) as r: audio = r.read()
    dest = pathlib.Path(dest); dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(audio)
    return True

def _xml(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def build(out=OUT, ledger_path=LEDGER, practice_dir=PRACTICE, render=True, today=None):
    out = pathlib.Path(out)
    ledger, results = load_json(ledger_path, {}), load_json(out / "results.json", {})
    words = pick(ledger, results, passage_texts(practice_dir), today=today)
    rendered = 0
    for w in words:
        clip = out / w["clip"]
        if render and not clip.exists():
            try:
                if tts(w["sentence"], clip): rendered += 1
            except Exception as e:
                print(f"sayit: clip for {w['id']} failed — {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
        if not clip.exists(): w["clip"] = ""        # the app falls back to text-only rather than a dead path
    dump_json(out / "words.json", {"version": 1, "written": _now(), "per_session": PER_SESSION, "words": words})
    return words, rendered

def _now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def pack(out=OUT, dest=None):
    """words.json + results.json + the clips → one zip, the only coach→app payload (see the header)."""
    out = pathlib.Path(out); dest = pathlib.Path(dest or out / "sayit.zip")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("words.json", "results.json"):
            if (out / name).exists(): z.write(out / name, name)
        for clip in sorted((out / "clips").glob("*.ogg")) if (out / "clips").is_dir() else []:
            z.write(clip, f"clips/{clip.name}")
    return dest

def score_one(audio, sentence, azure=None):
    """One attempt → the en-GB scripted scores. Needs the practice venv (Azure SDK) and ffmpeg."""
    azure = azure or _load("azure_pa")
    with tempfile.TemporaryDirectory() as td:
        wav = pathlib.Path(td) / "a.wav"
        _load("practice-ingest").to_wav(audio, wav)
        r = azure.dual_locale_assessment(str(wav), reference_text=sentence)
    gb = (r.get("en_gb") or {}).get("overall") or {}
    return {"accuracy": gb.get("accuracy"), "fluency": gb.get("fluency"), "pron": gb.get("pron"),
            "flagged": [w.get("word") for w in ((r.get("en_gb") or {}).get("flagged_words") or [])][:8]}

def status_for(rec, today=None, retire_at=RETIRE_AT, retire_hits=RETIRE_HITS, tutor_weeks=TUTOR_WEEKS):
    good = sum(1 for a in rec["attempts"] if (a.get("accuracy") or 0) >= retire_at)
    if good >= retire_hits: return "retired"
    first = min((a["at"][:10] for a in rec["attempts"]), default=None)
    if first and rec["attempts"]:
        age = (dt.date.fromisoformat(today or dt.date.today().isoformat()) - dt.date.fromisoformat(first)).days
        if age >= tutor_weeks * 7: return "tutor"
    return "active"

def score(src, out=OUT, scorer=None, today=None, log=print):
    """Every attempt in <src>/sayit/attempts not already scored → results.json. Idempotent by filename."""
    src, out = pathlib.Path(src), pathlib.Path(out)
    results = load_json(out / "results.json", {"version": 1, "words": {}})
    results.setdefault("words", {})
    done = {a.get("file") for r in results["words"].values() for a in r.get("attempts", [])}
    n = 0
    for side in sorted((src / "sayit" / "attempts").glob("*.json")) if (src / "sayit" / "attempts").is_dir() else []:
        meta = load_json(side, {})
        wid, sentence = meta.get("id"), meta.get("sentence")
        if not wid or not sentence: log(f"sayit: {side.name} has no id/sentence — skipped"); continue
        if side.name in done: continue
        audio = next((p for p in side.parent.glob(side.stem + ".*") if p.suffix.lower() != ".json"), None)
        if not audio: log(f"sayit: no audio beside {side.name} — skipped"); continue
        try:
            sc = (scorer or score_one)(audio, sentence)
        except Exception as e:
            log(f"sayit: scoring {side.name} failed — {type(e).__name__}: {str(e)[:120]}"); continue
        rec = results["words"].setdefault(wid, {"attempts": [], "best": None, "last": None, "status": "active"})
        rec["attempts"].append({"at": meta.get("started") or _now(), "file": side.name, **sc})
        accs = [a["accuracy"] for a in rec["attempts"] if a.get("accuracy") is not None]
        rec["best"] = max(accs) if accs else None
        rec["last"] = sc.get("accuracy")
        rec["status"] = status_for(rec, today)
        n += 1
    if n:
        results["updated"] = _now(); dump_json(out / "results.json", results)
    return n, results

def selftest():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        texts = ["He was the agent of imperialist expansion overseas. Short one. " +
                 "A far longer sentence that rambles on and on about imperialist policy and every possible qualification it might ever carry with it here. " +
                 "The man by the river watched the boat and the bridge and the light and the water and the sky.",
                 "The prophecy was never written down."]
        assert carrier("imperialist", texts) == "He was the agent of imperialist expansion overseas."
        assert carrier("prophecy", texts) == "The prophecy was never written down."
        assert carrier("absent", texts) is None
        ledger = {"words": {"imperialist": {"count": 3}, "prophecy": {"count": 2}, "once": {"count": 1},
                            "nowhere": {"count": 5}, "the": {"count": 2}, "watched": {"count": 1}},
                  "phonemes": {"i/ii": {"words": {"imperialist": 2}}, "s/z": {"words": {"prophecy": 1}}}}
        assert occurrences("imperialist", texts) == 2 and occurrences("the", texts) >= 9
        got = pick(ledger, {}, texts, today="2026-09-13")
        ids = [w["id"] for w in got]
        assert "imperialist" in ids and "prophecy" in ids, ids     # missed most of the times they were read
        assert "the" not in ids, ids                               # read 10 times, missed twice: not the problem
        assert "once" not in ids and "nowhere" not in ids and "watched" not in ids, ids   # under the count bar / no sentence
        assert ids[0] == "prophecy", ids                            # 2 of 1 reads beats 3 of 2
        assert got[0]["miss_rate"] >= 1.0 and got[0]["read_on"] == 1
        res = {"words": {"imperialist": {"status": "retired"}}}
        assert [w["id"] for w in pick(ledger, res, texts)] == ["prophecy"], "retired words are not served again"
        # status rules
        mk = lambda accs, first: {"attempts": [{"at": f"{first}T07:00:00Z", "accuracy": a} for a in accs]}
        assert status_for(mk([85.0, 91.0], "2026-09-01"), today="2026-09-13") == "retired"
        assert status_for(mk([85.0], "2026-09-13"), today="2026-09-13") == "active"
        assert status_for(mk([40.0, 55.0], "2026-08-01"), today="2026-09-13") == "tutor"
        assert status_for(mk([40.0, 88.0, 92.0], "2026-08-01"), today="2026-09-13") == "retired", "good scores win over age"
        # scoring: idempotent, sentence-driven, audio required
        src = td / "phone"; att = src / "sayit" / "attempts"; att.mkdir(parents=True)
        (att / "20260913T180402Z_imperialist.json").write_text(json.dumps(
            {"version": 1, "id": "imperialist", "word": "imperialist", "sentence": texts[0].split(".")[0] + ".",
             "started": "2026-09-13T18:04:02Z", "duration_s": 4.2}))
        (att / "20260913T180402Z_imperialist.m4a").write_bytes(b"audio")
        (att / "orphan.json").write_text(json.dumps({"id": "x", "sentence": "y"}))   # no audio beside it
        seen = []
        def fake(audio, sentence):
            seen.append(sentence); return {"accuracy": 88.0, "fluency": 80.0, "pron": 84.0, "flagged": []}
        out = td / "out"
        n, r = score(src, out, scorer=fake, today="2026-09-13", log=lambda *a: None)
        assert n == 1 and seen == ["He was the agent of imperialist expansion overseas."], (n, seen)
        assert r["words"]["imperialist"]["best"] == 88.0 and r["words"]["imperialist"]["status"] == "active"
        assert score(src, out, scorer=fake, today="2026-09-13", log=lambda *a: None)[0] == 0, "already scored"
        # a second good attempt retires it
        (att / "20260914T180402Z_imperialist.json").write_text(json.dumps(
            {"id": "imperialist", "sentence": texts[0].split(".")[0] + ".", "started": "2026-09-14T18:04:02Z"}))
        (att / "20260914T180402Z_imperialist.m4a").write_bytes(b"audio")
        n, r = score(src, out, scorer=fake, today="2026-09-14", log=lambda *a: None)
        assert n == 1 and r["words"]["imperialist"]["status"] == "retired", r["words"]["imperialist"]
        # build without rendering still writes a usable words.json (clip blanked, never a dead path)
        lp = td / "ledger.json"; lp.write_text(json.dumps(ledger))
        pd = td / "practice"; pd.mkdir()
        ws, rendered = build(out, lp, pd, render=False, today="2026-09-13")
        assert rendered == 0 and json.loads((out / "words.json").read_text())["per_session"] == PER_SESSION
        assert all(w["clip"] == "" for w in ws), ws
        # the zip is the whole coach→app payload
        (out / "clips").mkdir(exist_ok=True); (out / "clips" / "x.ogg").write_bytes(b"ogg")
        z = pack(out)
        import zipfile as _z
        names = sorted(_z.ZipFile(z).namelist())
        assert names == ["clips/x.ogg", "results.json", "words.json"], names
    print("sayit.py selftest: OK")

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", action="store_true", help="rebuild logs/sayit/words.json and the model clips")
    ap.add_argument("--score", action="store_true", help="score the attempts under --dir")
    ap.add_argument("--dir", type=pathlib.Path, help="a folder laid out like Documents/MinimalPairs")
    ap.add_argument("--no-render", action="store_true", help="skip Azure text-to-speech")
    ap.add_argument("--pack", action="store_true", help="write logs/sayit/sayit.zip (the coach→app payload)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return selftest()
    if not (a.build or a.score or a.pack): ap.error("--build, --score or --pack")
    if a.score:
        if not a.dir: ap.error("--score needs --dir")
        n, r = score(a.dir)
        act = sum(1 for w in r["words"].values() if w["status"] == "active")
        print(f"sayit: {n} attempt(s) scored; {act} word(s) active, "
              f"{sum(1 for w in r['words'].values() if w['status'] == 'retired')} retired, "
              f"{sum(1 for w in r['words'].values() if w['status'] == 'tutor')} for the tutor")
    if a.build:
        ws, rendered = build(render=not a.no_render)
        print(f"sayit: {len(ws)} word(s) to say" + (f", {rendered} clip(s) rendered" if rendered else "")
              + (" — " + ", ".join(w["id"] for w in ws[:5]) if ws else " (nothing flagged twice yet)"))
    if a.pack or a.build:
        z = pack()
        print(f"sayit: packed {z.relative_to(REPO)} ({z.stat().st_size // 1024} KB)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
