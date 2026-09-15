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
  sayit/scores/<ts>_<id>.json app → coach: the score the PHONE computed, instantly, with the learner's own
                              separate Azure resource. This is the normal path: the app must not depend on
                              a sync running to give feedback, or a missed sync costs a day of practice.
                              The coach only scores an attempt itself when the phone could not (no key,
                              no network, Azure error) — the fallback, never the rule.

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
COMMON_MIN_READS = 10    # ...but the rate is only believable when the occurrences were actually counted.
                         # `library/` is gitignored, so in a cloud container the passage text is usually
                         # missing and read_on collapses towards zero — on 2026-09-15 "under" came out at
                         # 4 flags in 1 read, a rate of 4.0, and seven of the ten words offered were
                         # function words ("all", "its", "come", "which"). So a word inside the commonest
                         # TOO_COMMON needs this many COUNTED occurrences before its rate is trusted;
                         # without them it is dropped, and rarity breaks ties among the rest.
RETIRE_AT, RETIRE_HITS = 80.0, 2
MIN_COMPLETENESS = 80.0   # a sentence he only half said never counts towards retiring the word
MAX_WPM = 240.0           # above this nobody is speaking: the recording stopped before the sentence did
TUTOR_WEEKS = 3

# --- new words from the reading (source "new") ---------------------------------------------
# A different problem from a flagged word. A flagged word is a motor habit to break: he says it
# his way and Azure marks it. A word he looked up while reading he has never said at all — there
# is no habit, there is no model. Hearing it once and saying it is exactly the intervention, and
# it is the half Anki cannot give him: a card he reads silently teaches the meaning and never
# tells him whether the mouth was right.
VOCAB = REPO / "logs" / "reading" / "vocab.json"
LIBRARY = REPO / "library"
ALT_SENTENCES = 3        # how many carrier sentences a word may carry, counting the first
NEW_ACTIVE = 6           # how many new words ride along with the flagged ones
NEW_MIN_WORDS = 6        # a usage fragment shorter than this is not a sentence to repeat
NEW_MAX_WORDS = 30
TOO_COMMON = 2000        # flagged path: a word this common, flagged, is connected speech, not a problem
TOO_COMMON_NEW = 2000    # new-word path. Raised to 15000 on 2026-09-15 and put straight back the same day:
                         # asked which lookups were mis-taps, he named function words only — "and, that,
                         # in, under, all, its, come, which, only, our, situation", every one inside the
                         # commonest ~1000 — and said he MEANT hatred, haste, spectacle, medieval, swift,
                         # glimpse, comrades, sheer, midst. So the automatic screen only removes the
                         # finger-slips, and judging which real word is worth his mouth is HIS call, made
                         # by deleting the word in KOReader's Vocabulary Builder (koreader-pull then drops
                         # it — see `dropped`). A threshold cannot tell a tap he meant from one he did not.
WORDLISTS = REPO / ".cache" / "minimal-pairs" / "data" / "sources"

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

def book_texts(library=LIBRARY):
    """Every processed book's full text. `library/` is gitignored (the EPUBs are copyrighted) and is
    rebuilt from Drive at the start of each cloud-sync run, so this is present when the build runs and
    simply empty when it is not — in which case a word keeps the one sentence it already had."""
    out = []
    for f in sorted(pathlib.Path(library).glob("*.json")) if pathlib.Path(library).is_dir() else []:
        d = load_json(f, {})
        t = " ".join(c.get("text", "") for c in (d.get("chunks") or []) if isinstance(c, dict))
        if t: out.append(t)
    return out

def looks_clean(t):
    """Whether a sentence pulled from a scanned book is fit to be read aloud.

    The extraction carries the page's debris — footnote numbers welded to the next word ("5See"),
    column markers ("1J"), stray single capitals. A human skims past them; a neural voice reads them
    out and the assessment then scores him against a reference text nobody would say."""
    if re.search(r"\b(?=\w*\d)(?=\w*[A-Za-z])\w+\b", t): return False      # 1J, 5See, p12
    singles = [w for w in re.findall(r"\b[A-Za-z]\b", t) if w not in ("a", "A", "I")]
    return len(singles) == 0

def carriers(word, texts, keep=None, limit=ALT_SENTENCES, min_words=6, max_words=30):
    """Up to [limit] DIFFERENT sentences from the books in which [word] actually appears, [keep] first.

    Practising one sentence over and over is blocked practice: it makes the rehearsed sentence better
    and does not carry. Varying the carrier is the contextual-interference effect, which costs
    accuracy during practice and buys retention and transfer — and transfer is exactly what his own
    data says is missing (2026-09-15: 98-99 on the sentence he had just heard, the same words flagged
    inside fifteen to eighty-four minutes of continuous reading).

    Never invented. A word with only one sentence in the books keeps the one it has."""
    rx = re.compile(r"\b" + re.escape(word) + r"\b", re.I)
    out = [keep] if keep else []
    seen = {tidy(keep)} if keep else set()
    cands = [t for text in texts for t in (tidy(x) for x in sentences(text))
             if rx.search(t) and min_words <= len(t.split()) <= max_words and t[-1:] in ".!?"
             and looks_clean(t)]
    for t in sorted(cands, key=lambda x: len(x.split())):   # shortest first: easier to hold and repeat
        if t in seen: continue
        seen.add(t); out.append(t)
        if len(out) >= limit: break
    return out

def todays(items, today=None):
    """Which of a word's sentences is the live one. Rotates by DAY, not by run: cloud-sync runs
    several times a day and the sentence must not change under him mid-session."""
    if not items: return None
    d = dt.date.fromisoformat(today or dt.date.today().isoformat())
    return items[d.toordinal() % len(items)]

def _load(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def flagged_since(rec, last_flagged):
    """Whether the ledger has flagged this word again SINCE its last attempt — the one thing that
    brings a retired word back."""
    if not last_flagged: return False
    last_try = max((a["at"][:10] for a in rec.get("attempts") or []), default=None)
    return bool(last_try) and last_flagged[:10] > last_try

def pick(ledger, results, texts, max_active=MAX_ACTIVE, min_flagged=MIN_FLAGGED, min_rate=MIN_RATE,
         today=None, lists=None):
    """Words he actually gets wrong, worst rate first, each with a sentence he has read.
    Ranked by how OFTEN he misses the word, not by how often it appears."""
    today = today or dt.date.today().isoformat()
    _known, freq = lists if lists is not None else known_words()
    cand = []
    for w, W in (ledger.get("words") or {}).items():
        n = W.get("count", 0)
        if n < min_flagged: continue
        rec = (results.get("words") or {}).get(w) or {}
        # A retired word comes BACK when a later read flags it again (2026-09-15). On his first real
        # Say-it session every word scored 98-99 — genuine, the durations are 82-131 wpm of real
        # speech — because he had just heard the model and was saying one sentence with full
        # attention. The reads that flagged those same words are 15 to 84 minutes of continuous
        # Arendt. So a high Say-it score does not mean the word is fixed; it means it is fixable
        # when attended to, and the failure lives in connected speech under load. Retiring for ever
        # on that evidence would hollow the drill out with false victories.
        if rec.get("status") in ("retired", "tutor") and not flagged_since(rec, W.get("last")): continue
        seen = occurrences(w, texts)
        rate = min(n / seen, 1.0) if seen else 1.0   # >1 would mean more flags than readings: uncounted
        if rate < min_rate: continue             # a word read 200 times and missed 3 is not the problem
        rank = freq.get(w.lower(), 10 ** 9)
        if rank < TOO_COMMON and seen < COMMON_MIN_READS: continue
        s = carrier(w, texts)
        if not s: continue                       # never invent a sentence he did not read
        cls = [c for c, L in (ledger.get("phonemes") or {}).items() if w in (L.get("words") or {})]
        cand.append((round(rate, 3), n, {"id": w, "word": w, "sentence": s, "clip": f"clips/{w}.ogg", "ipa": "",
                                         "classes": sorted(cls), "flagged_on": n, "read_on": seen,
                                         "miss_rate": round(rate, 2), "rank": rank, "added": today}))
    # rate first, then the RARER word: with read_on unreliable the rates bunch at 1.0, and
    # "imperialist" is a better use of his evening than "our".
    cand.sort(key=lambda t: (-t[0], -t[2]["rank"], -t[1], t[2]["id"]))
    return [c[2] for c in cand[:max_active]]

def known_words(src=WORDLISTS):
    """British pronunciation dictionary + frequency list, as a SOFT signal (see new_words).
    Missing files simply mean the signal is unavailable, never that everything is junk."""
    import csv
    known, freq = set(), {}
    try:
        for row in csv.reader(open(pathlib.Path(src) / "britfone.main.3.0.1.csv", encoding="utf-8")):
            if row: known.add(row[0].strip().lower().split("(")[0])
    except OSError: pass
    try:
        for i, line in enumerate(open(pathlib.Path(src) / "en_50k.txt", encoding="utf-8")):
            w = line.split()
            if w: freq.setdefault(w[0].lower(), i)
    except OSError: pass
    return known, freq

def tidy(text):
    """KOReader's stored context carries its highlight marks: a space before the punctuation that
    follows the looked-up word, and the hyphen of a line break the page kept. Left in, the clip
    reads them as pauses and the reference text no longer matches what anyone would say."""
    t = re.sub(r"\s+", " ", text or "").strip()
    t = re.sub(r"\s+([,.;:!?\u2019\u201d)])", r"\1", t)
    t = re.sub(r"([(\u2018\u201c])\s+", r"\1", t)
    t = t.replace(" | ", " ")                     # KOReader's page-break marker
    # "twentieth- century" is a hyphenated compound split by the page, far more often than it is one
    # word broken across lines; keeping the hyphen is right in the first case and harmless in the
    # second, since the voice reads "imperial-ism" and "imperialism" the same way.
    t = re.sub(r"(\w)-\s+(\w)", r"\1-\2", t)
    t = re.sub(r"\s-(\w)", r" \1", t)              # a stray leading hyphen: as -well
    # A footnote or page marker the extraction left on the end — "...favors an imperialist policy." P."
    # — is not part of the sentence, and the voice reads it aloud as a word.
    m = re.search(r"""([.!?][\u201d\u2019"']?)\s+[A-Za-z]{1,2}\.\s*$""", t)
    return t[:m.end(1)] if m else t

def usable_usage(word, usage, min_words=NEW_MIN_WORDS, max_words=NEW_MAX_WORDS):
    """The one sentence of KOReader's stored context that holds the word, or None.

    The Vocabulary Builder keeps a ~300-character window, not a sentence, so it usually starts and
    ends mid-clause. Repeating half a clause is a worse motor task than repeating a sentence, so
    the window is cut at sentence boundaries and only a whole one that contains the word is used."""
    rx = re.compile(r"\b" + re.escape(word) + r"\b", re.I)
    cands = [t for t in (tidy(x) for x in sentences(usage or ""))
             # The window is cut at both ends: the first piece starts mid-clause (lower case) and the
             # last one stops mid-clause (no terminal stop). Repeating half a clause is a worse motor
             # task than repeating a sentence, so only a whole one counts.
             if t[:1].isupper() and t[-1:] in ".!?" and rx.search(t)
             and min_words <= len(t.split()) <= max_words]
    return min(cands, key=lambda t: len(t.split())) if cands else None

def worth_saying(word, freq, too_common=TOO_COMMON_NEW):
    """Whether a looked-up word is worth a slot, by the word alone.

    Also applied to the words ALREADY on the list, so tightening the bar clears out what it now
    rejects instead of leaving it standing for ever."""
    w = (word or "").strip()
    if not w or not w.isalpha() or len(w) < 3: return False
    if not re.search(r"[aeiouy]", w.lower()): return False   # OCR damage, not a word
    if w[:1].isupper(): return False                          # Volga, Comintern: a name, not vocabulary
    return freq.get(w.lower(), 10 ** 9) >= too_common

def new_words(vocab, results, limit=NEW_ACTIVE, today=None, lists=None):
    """Words he looked up while reading, newest first, each in a sentence he actually met it in.

    Three hard rejects, and one soft one:
      * shape — not alphabetic, under three letters, or no vowel: OCR damage, not a word;
      * a capital letter inside the sentence — Volga, Comintern, Quisling are names, not vocabulary;
      * the commonest TOO_COMMON words — he has heard "that" and "in", they need no model.
    The wordlists are NOT a gate. Tried as one they threw away conglomeration, erudition,
    lamentation, denunciation, portentous and conflagration — 33 good words to catch 4 bits of OCR
    damage. So a word the lists do not recognise is merely ranked last: newer, recognised words
    come first and in practice he never reaches the junk."""
    today = today or dt.date.today().isoformat()
    known, freq = lists if lists is not None else known_words()
    out = []
    for v in reversed(vocab.get("lookups") or []):          # newest first: he just met it in context
        w = (v.get("word") or "").strip()
        if not w or v.get("carded") or v.get("dropped"): continue
        if not worth_saying(w, freq): continue
        wid = "new-" + w.lower()
        st = ((results.get("words") or {}).get(wid) or {}).get("status")
        if st in ("retired", "tutor", "parked"): continue
        s = usable_usage(w, v.get("usage"))
        if not s: continue
        recognised = w.lower() in known or w.lower() in freq
        out.append((0 if recognised else 1, len(out),
                    {"id": wid, "word": w, "sentence": s, "clip": f"clips/{wid}.ogg", "ipa": "",
                     "classes": [], "source": "new", "book": v.get("book") or "", "added": today}))
    out.sort(key=lambda t: (t[0], t[1]))                    # recognised first, then newest
    return [o[2] for o in out[:limit]]

def mark_used(path, vocab, words):
    """Claim these lookups so nothing offers them twice.

    `carded` is the flag reading-cards.py already sets and respects; Say-it took the new words over
    on 2026-09-15, so it is now the one that sets it. One flag, whichever side spends the lookup."""
    if not words: return 0
    want, n = {w.lower() for w in words}, 0
    for v in vocab.get("lookups") or []:
        if (v.get("word") or "").lower() in want and not v.get("carded"):
            v["carded"] = True; n += 1
    if n: dump_json(path, vocab)
    return n

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

def build(out=OUT, ledger_path=LEDGER, practice_dir=PRACTICE, render=True, today=None, vocab_path=VOCAB):
    """The two halves of the drill, in one words.json.

    `flagged` words come from the reads: a motor habit to break. `new` words come from the reading
    lookups: a word he has never said, where the model clip IS the teaching and Anki's silent card
    could never tell him whether the mouth was right. Both are the same unit — the word in a
    sentence he actually met — so the app needs no change to show them; `source` is an extra field
    an older build simply ignores."""
    out = pathlib.Path(out)
    ledger, results = load_json(ledger_path, {}), load_json(out / "results.json", {})
    words = [dict(w, source="flagged") for w in pick(ledger, results, passage_texts(practice_dir), today=today)]
    # New words must SURVIVE a rebuild. The claim (`carded`) stops a lookup being picked twice, so
    # a word dropped from the list after one build would be gone for good, spent without ever being
    # served. So the ones already on the list stay until they retire or park, and only the room left
    # is topped up.
    vocab = load_json(vocab_path, {})
    done = {w for w, r in (results.get("words") or {}).items()
            if r.get("status") in ("retired", "tutor", "parked")}
    _known, _freq = known_words()
    standing = [w for w in (load_json(out / "words.json", {}).get("words") or [])
                if w.get("source") == "new" and w.get("id") not in done
                and worth_saying(w.get("word"), _freq)]
    fresh = new_words(vocab, results, limit=max(0, NEW_ACTIVE - len(standing)), today=today)
    words += standing + fresh
    mark_used(vocab_path, vocab, [w["word"] for w in fresh])

    # Each word carries every sentence the BOOKS give it, and today's is promoted to `sentence`.
    # Varying the carrier is the point (see carriers()); rotating by day rather than by run keeps it
    # from changing under him mid-session. `sentence`/`clip` stay the live pair so the build already
    # on the phone works unchanged; `sentences` is additive, for an app build that picks per attempt.
    books = book_texts()
    rendered = 0
    for w in words:
        alts = carriers(w["word"], books, keep=w["sentence"]) or [w["sentence"]]
        w["sentences"] = [{"text": t, "clip": f"clips/{w['id']}-{i}.ogg"} for i, t in enumerate(alts)]
        for entry in w["sentences"]:
            clip = out / entry["clip"]
            if render and not clip.exists():
                try:
                    if tts(entry["text"], clip): rendered += 1
                except Exception as e:
                    print(f"sayit: clip for {w['id']} failed — {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
            if not clip.exists(): entry["clip"] = ""
        live = todays(w["sentences"], today)
        w["sentence"], w["clip"] = live["text"], live["clip"]
    dump_json(out / "words.json", {"version": 1, "written": _now(), "per_session": PER_SESSION,
                                   "words": words})
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
            "completeness": gb.get("completeness"),
            "flagged": [w.get("word") for w in ((r.get("en_gb") or {}).get("flagged_words") or [])][:8]}

def status_for(rec, today=None, retire_at=RETIRE_AT, retire_hits=RETIRE_HITS, tutor_weeks=TUTOR_WEEKS):
    # Accuracy alone would retire a word off a sentence he only half said: Azure scores the words
    # it heard, so three clear words out of twenty can score high. An attempt counts towards
    # retirement only when he actually said the sentence (completeness is absent on an unscripted
    # answer, and absent never blocks).
    real = [a for a in rec["attempts"] if not a.get("void")]
    good = sum(1 for a in real
               if (a.get("accuracy") or 0) >= retire_at
               and (a.get("completeness") is None or a["completeness"] >= MIN_COMPLETENESS))
    if good >= retire_hits: return "retired"
    first = min((a["at"][:10] for a in real), default=None)
    if first and real:
        age = (dt.date.fromisoformat(today or dt.date.today().isoformat()) - dt.date.fromisoformat(first)).days
        # A FLAGGED word still failing after three weeks is a motor problem a human should hear. A
        # NEW word is not: he simply has not got it yet, or it is too rare to be worth more of his
        # evening. It parks, and the slot goes to the next word off the reading.
        if age >= tutor_weeks * 7: return "parked" if str(rec.get("id", "")).startswith("new-") else "tutor"
    return "active"

def phone_score(src, stem):
    """The score the phone already computed for this attempt, if any (sayit/scores/<stem>.json)."""
    f = pathlib.Path(src) / "sayit" / "scores" / f"{stem}.json"
    d = load_json(f, None)
    if not isinstance(d, dict) or d.get("accuracy") is None: return None
    return {"accuracy": d.get("accuracy"), "fluency": d.get("fluency"), "pron": d.get("pron"),
            "completeness": d.get("completeness"),
            "flagged": list(d.get("flagged") or [])[:8], "source": d.get("source") or "phone"}

def void_attempt(meta):
    """Why this attempt is not a reading of the sentence, or None when it is one.

    A recording that stopped early — a mis-tap, a phone locking, the button let go — comes back
    from Azure as every word omitted, which is a real assessment of what it heard and a score of
    zero for the learner. It is the Say-it twin of practice-review's MIN_WORDS rule: a void take
    must count as nothing, not as a failure. Duration is the phone's own and does not depend on
    Azure having understood anything."""
    sec, words = meta.get("duration_s"), len((meta.get("sentence") or "").split())
    if not sec or not words: return None
    wpm = words / (sec / 60.0)
    if wpm > MAX_WPM:
        return f"{sec:.1f}s for {words} words ({wpm:.0f} wpm) — the recording stopped before the sentence did"
    return None

def score(src, out=OUT, scorer=None, today=None, log=print):
    """Every attempt in <src>/sayit/attempts not already recorded → results.json. Idempotent by filename.
    The phone's own score is used when present (that is the normal path and costs nothing here); the
    audio is only sent to Azure when the phone could not score it."""
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
        why = void_attempt(meta)
        if why:
            # Recorded, so it is never scored or re-examined, but it is not an attempt at the word:
            # it sets no score, starts no tutor clock and counts towards nothing.
            log(f"sayit: {side.name} void — {why}")
            rec = results["words"].setdefault(wid, {"id": wid, "attempts": [], "best": None, "last": None, "status": "active"})
            rec["attempts"].append({"at": meta.get("started") or _now(), "file": side.name, "void": True, "note": why})
            n += 1
            continue
        sc = phone_score(src, side.stem)
        if sc is None:
            audio = next((p for p in side.parent.glob(side.stem + ".*") if p.suffix.lower() != ".json"), None)
            if not audio: log(f"sayit: no audio beside {side.name} and no phone score — skipped"); continue
            try:
                sc = dict((scorer or score_one)(audio, sentence), source="cloud")
            except Exception as e:
                log(f"sayit: scoring {side.name} failed — {type(e).__name__}: {str(e)[:120]}"); continue
        rec = results["words"].setdefault(wid, {"id": wid, "attempts": [], "best": None, "last": None, "status": "active"})
        rec["attempts"].append({"at": meta.get("started") or _now(), "file": side.name, **sc})
        accs = [a["accuracy"] for a in rec["attempts"] if not a.get("void") and a.get("accuracy") is not None]
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
        LISTS = (set(), {"the": 1, "prophecy": 9000, "imperialist": 31690})
        got = pick(ledger, {}, texts, today="2026-09-13", lists=LISTS)
        ids = [w["id"] for w in got]
        assert "imperialist" in ids and "prophecy" in ids, ids     # missed most of the times they were read
        assert "the" not in ids, ids                               # read 10 times, missed twice: not the problem
        assert "once" not in ids and "nowhere" not in ids and "watched" not in ids, ids   # under the count bar / no sentence
        assert ids[0] == "imperialist", ids     # both rates clamp to 1.0, so the rarer word goes first
        assert all(w["miss_rate"] <= 1.0 for w in got), "more flags than readings is uncounted, not terrible"
        # a common word whose occurrences were never counted is dropped, not promoted
        blind = {"words": {"under": {"count": 4}}, "phonemes": {}}
        SENT = "The whole thing went under the water again. "
        assert pick(blind, {}, [SENT], today="2026-09-13",
                    lists=(set(), {"under": 384})) == [], "top-2000 word, 1 counted read: not trusted"
        assert [w["id"] for w in pick(blind, {}, [SENT * 12], today="2026-09-13",
                                      lists=(set(), {"under": 384}))] == ["under"], "counted enough: trusted"
        assert [w["id"] for w in pick(blind, {}, [SENT], today="2026-09-13",
                                      lists=(set(), {}))] == ["under"], "a rare word needs no such proof"
        res = {"words": {"imperialist": {"status": "retired",
                                         "attempts": [{"at": "2026-09-20T07:00:00Z", "accuracy": 99.0}]}}}
        assert [w["id"] for w in pick(ledger, res, texts, lists=LISTS)] == ["prophecy"], "retired words are not served again"
        # ...unless a later read flags it again: saying one sentence well is not the same as saying
        # it well inside eighty minutes of Arendt
        assert not flagged_since(res["words"]["imperialist"], "2026-09-19")
        assert flagged_since(res["words"]["imperialist"], "2026-09-21")
        back = dict(ledger, words=dict(ledger["words"], imperialist={"count": 3, "last": "2026-09-21"}))
        assert "imperialist" in [w["id"] for w in pick(back, res, texts, lists=LISTS)], "flagged again: back"
        # status rules
        mk = lambda accs, first: {"attempts": [{"at": f"{first}T07:00:00Z", "accuracy": a} for a in accs]}
        assert status_for(mk([85.0, 91.0], "2026-09-01"), today="2026-09-13") == "retired"
        assert status_for(mk([85.0], "2026-09-13"), today="2026-09-13") == "active"
        assert status_for(mk([40.0, 55.0], "2026-08-01"), today="2026-09-13") == "tutor"
        assert status_for(mk([40.0, 88.0, 92.0], "2026-08-01"), today="2026-09-13") == "retired", "good scores win over age"
        half = {"attempts": [{"accuracy": 95.0, "completeness": 30.0, "at": "2026-09-01"},
                             {"accuracy": 95.0, "completeness": 30.0, "at": "2026-09-02"}]}
        assert status_for(half, today="2026-09-13") == "active", "a half-said sentence never retires the word"
        half["attempts"][1]["completeness"] = 100.0
        assert status_for(half, today="2026-09-13") == "active", "one full attempt is not two"
        half["attempts"][0]["completeness"] = 100.0
        assert status_for(half, today="2026-09-13") == "retired"
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
        assert r["words"]["imperialist"]["attempts"][0]["source"] == "cloud", "no phone score: cloud fallback"
        assert score(src, out, scorer=fake, today="2026-09-13", log=lambda *a: None)[0] == 0, "already scored"
        # a second good attempt retires it
        (att / "20260914T180402Z_imperialist.json").write_text(json.dumps(
            {"id": "imperialist", "sentence": texts[0].split(".")[0] + ".", "started": "2026-09-14T18:04:02Z"}))
        (att / "20260914T180402Z_imperialist.m4a").write_bytes(b"audio")
        n, r = score(src, out, scorer=fake, today="2026-09-14", log=lambda *a: None)
        assert n == 1 and r["words"]["imperialist"]["status"] == "retired", r["words"]["imperialist"]
        # the phone's own score is taken as-is: no audio needed, Azure never called here
        sc_dir = src / "sayit" / "scores"; sc_dir.mkdir(parents=True)
        stem = "20260915T070000Z_prophecy"
        (att / f"{stem}.json").write_text(json.dumps(
            {"id": "prophecy", "sentence": "The prophecy was never written down.", "started": "2026-09-15T07:00:00Z"}))
        (sc_dir / f"{stem}.json").write_text(json.dumps(
            {"version": 1, "id": "prophecy", "at": "2026-09-15T07:00:00Z", "source": "phone-azure",
             "accuracy": 62.0, "fluency": 55.0, "pron": 58.0, "completeness": 100.0,
             "flagged": ["prophecy"]}))
        before = len(seen)
        n, r = score(src, out, scorer=fake, today="2026-09-15", log=lambda *a: None)
        assert n == 1 and len(seen) == before, "phone score used; the cloud scorer was not called"
        pr_ = r["words"]["prophecy"]
        assert pr_["last"] == 62.0 and pr_["attempts"][0]["source"] == "phone-azure" and pr_["status"] == "active", pr_
        assert pr_["attempts"][0]["completeness"] == 100.0, "the phone's completeness is kept, not dropped"
        # a take that stopped early is void: recorded so it is never rescored, but it scores nothing
        assert void_attempt({"duration_s": 1.2, "sentence": " ".join(["w"] * 22)}), "1.2s for 22 words is void"
        assert void_attempt({"duration_s": 9.0, "sentence": " ".join(["w"] * 22)}) is None, "9s for 22 words is a reading"
        assert void_attempt({"sentence": "no duration recorded"}) is None, "no duration: never guess it void"
        vstem = "20260916T070000Z_prophecy"
        (att / f"{vstem}.json").write_text(json.dumps(
            {"id": "prophecy", "sentence": "The prophecy was never written down.", "started": "2026-09-16T07:00:00Z",
             "duration_s": 0.4}))
        (att / f"{vstem}.m4a").write_bytes(b"audio")
        before = len(seen)
        n, r = score(src, out, scorer=fake, today="2026-09-16", log=lambda *a: None)
        pr_ = r["words"]["prophecy"]
        assert n == 1 and len(seen) == before, "a void take is never sent to Azure"
        assert pr_["attempts"][-1]["void"] is True and pr_["last"] == 62.0, "void leaves the real score standing"
        assert score(src, out, scorer=fake, today="2026-09-16", log=lambda *a: None)[0] == 0, "void is recorded once"
        vonly = {"attempts": [{"at": "2026-08-01", "file": "x.json", "void": True}]}
        assert status_for(vonly, today="2026-09-16") == "active", "void attempts start no tutor clock"
        # --- new words from the reading ------------------------------------------------------
        assert tidy("spectacle , but") == "spectacle, but"
        assert tidy("of | twentieth- century") == "of twentieth-century"
        assert tidy("as -well.") == "as well."
        assert tidy("favors an imperialist policy.\u201d P.") == "favors an imperialist policy.\u201d", "footnote marker"
        assert tidy("He met Mr. Smith at the door.") == "He met Mr. Smith at the door.", "a real initial survives"
        full = "The theory that the Jews are always the scapegoat implies that anyone might have been."
        assert usable_usage("scapegoat", "cut mid clause and then. " + full) == full
        assert usable_usage("scapegoat", "a scapegoat sentence with no terminal stop") is None, "tail cut"
        assert usable_usage("scapegoat", "But nothing here names it at all.") is None, "must hold the word"
        voc = {"lookups": [
            {"word": "Volga", "usage": "He walked to the Volga and stopped there for a while."},
            {"word": "that", "usage": "It was that thing he had wanted for a very long time."},
            {"word": "xy", "usage": "Too short to be xy a word at all in this sentence."},
            {"word": "Apmsesinsy", "usage": "A word Apmsesinsy the scanner invented on this page here."},
            {"word": "deptived", "usage": "They were deptived of every right they had ever held."},
            {"word": "spent", "usage": "Nothing here.", "carded": True},
            {"word": "scapegoat", "usage": "unfinished start. " + full},
        ]}
        voc["lookups"].append({"word": "erased", "usage": "He erased the whole thing in one go.", "dropped": True})
        got = new_words(voc, {}, lists=({"scapegoat"}, {"that": 3, "scapegoat": 16064}))
        ids = [w["id"] for w in got]
        assert "new-volga" not in ids, "a proper noun is a name, not vocabulary"
        assert "new-that" not in ids, "too common to need a model"
        assert "new-xy" not in ids and "new-spent" not in ids, "shape reject; already spent"
        assert "new-erased" not in ids, "deleted in KOReader: his call, and it stands"
        assert "new-apmsesinsy" not in ids, "capitalised OCR damage falls to the proper-noun rule"
        assert ids[0] == "new-scapegoat" and got[0]["sentence"] == full, got
        assert ids[-1] == "new-deptived", "unrecognised ranks last, it is not thrown away"
        assert got[0]["source"] == "new"
        assert new_words(voc, {"words": {"new-scapegoat": {"status": "retired"}}},
                         lists=({"scapegoat"}, {}))[0]["id"] != "new-scapegoat"
        # a word he knows is a mis-tap, not a lookup: the bar is deliberateness, not meaning
        assert not worth_saying("and", {"and": 7}), "a function word is a finger-slip"
        assert worth_saying("haste", {"haste": 10391}), "he meant this one: not the screen's call"
        assert worth_saying("scapegoat", {"scapegoat": 16064})
        assert worth_saying("conglomeration", {}), "not in the 50k list at all: the best kind of target"
        assert not worth_saying("Volga", {}) and not worth_saying("xy", {}) and not worth_saying("psst", {})
        vp = td / "vocab.json"; dump_json(vp, voc)
        v2 = load_json(vp, {}); assert mark_used(vp, v2, ["scapegoat"]) == 1
        assert [x for x in load_json(vp, {})["lookups"] if x["word"] == "scapegoat"][0]["carded"] is True
        assert mark_used(vp, load_json(vp, {}), ["scapegoat"]) == 0, "claimed once"
        # build without rendering still writes a usable words.json (clip blanked, never a dead path)
        lp = td / "ledger.json"; lp.write_text(json.dumps(ledger))
        pd = td / "practice"; pd.mkdir()
        ws, rendered = build(out, lp, pd, render=False, today="2026-09-13", vocab_path=vp)
        assert rendered == 0 and json.loads((out / "words.json").read_text())["per_session"] == PER_SESSION
        assert all(w["clip"] == "" for w in ws), ws
        # every word carries its sentences; the live one rotates by day, never mid-day
        assert all(w["sentences"] and w["sentence"] == todays(w["sentences"], "2026-09-13")["text"] for w in ws), ws
        three = ["A one.", "B two.", "C three."]
        assert todays(three, "2026-09-13") != todays(three, "2026-09-14"), "a new day, a new carrier"
        assert todays(three, "2026-09-13") == todays(three, "2026-09-13"), "stable within the day"
        assert todays([], "2026-09-13") is None and todays(["only one."], "2026-09-13") == "only one."
        BOOK = ("The scapegoat was chosen long before anyone asked why. " * 1 +
                "Nobody wanted to be the scapegoat of that particular year at all. " +
                "He said scapegoat again and again until it meant nothing to him.")
        c = carriers("scapegoat", [BOOK], keep="The scapegoat was chosen long before anyone asked why.")
        assert len(c) == 3 and c[0] == "The scapegoat was chosen long before anyone asked why.", c
        assert len(set(c)) == 3, "three different sentences, none repeated"
        assert carriers("absent", [BOOK], keep="Kept anyway.") == ["Kept anyway."], "never invented"
        assert not looks_clean("During the imperialist period neither the state nor the 1J, A.")
        assert not looks_clean("5See the very instructive note on this imperialist question.")
        assert looks_clean("The more conspicuous the power of totalitarianism the more secret it becomes.")
        assert looks_clean("I gave a talk about it."), "a and I are words, not debris"
        assert carriers("noise", ["The noise was the 1J, A. The noise was plain and clear enough."],
                        keep=None) == ["The noise was plain and clear enough."], "page debris is not a carrier"
        assert {w["source"] for w in ws} <= {"flagged", "new"} and any(w["source"] == "new" for w in ws), ws
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
