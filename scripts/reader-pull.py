#!/usr/bin/env python3
"""The app's reader → repo (the successor of koreader-pull.py for the same three things).

The Minimal Pairs app reads the EPUB now (its docs/CONTRACT.md, "Reader"). It writes, under the phone
folder Documents/MinimalPairs/reading (Drive EnglishPractice/pairs/reading through Autosync):

  progress.json      the position in every book opened there, keyed by KOReader's partial MD5
  vocab.jsonl        one line per word saved (op add, with the sentence) or deleted (op delete)
  time/<ts>.json     one stretch of reading each: started, ended, seconds, book, from/to percentage

This folds a copy of that folder into the SAME files koreader-pull.py maintains, so nothing downstream
changes (reading-hub, weekly-rollup, sayit's `new` words, daily-readout):

  logs/reading/vocab.json     lookups with ids "app:<word>"; a delete marks `dropped` (and `carded`, so
                              Say it never offers it) and NEVER erases — saving the word again brings it
                              back. Only the lines after the last fold are applied (reader-state.json).
  logs/reading/daily.json     {date: {min, pages, books, ko_min, app_min}} — the app's minutes are added
                              to KOReader's for the same day (Europe/London), each time file folded once
                              (logs/reading/reader-state.json remembers which).
  logs/reading/progress.json  {slug: {..., source: "app"}} through books.json's partial_md5; the newer
                              timestamp wins against a KOReader/kosync position.

Usage:  python3 scripts/reader-pull.py --dir <copy of reading/>     python3 scripts/reader-pull.py --selftest
Load, harvest, pointer — never a score; nothing here reaches tracking.tsv.
"""
import datetime as dt, importlib.util, json, pathlib, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
RDIR = REPO / "logs" / "reading"
VOCAB, DAILY, PROGRESS, BOOKS = RDIR / "vocab.json", RDIR / "daily.json", RDIR / "progress.json", RDIR / "books.json"
STATE = RDIR / "reader-state.json"
CLEANUP = RDIR / "cleanup.json"
SOURCE = "app"

def _ko():
    spec = importlib.util.spec_from_file_location("koreader_pull", REPO / "scripts" / "koreader-pull.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def load(p, default):
    try: return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError): return default

def dump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)

def parse_iso(s):
    try: return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError): return None

def local_date(when):
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/London")
    except Exception:
        tz = dt.timezone.utc
    return when.astimezone(tz).strftime("%Y-%m-%d")

def read_events(path):
    """vocab.jsonl → the events in file order; a broken line is skipped, never fatal."""
    out = []
    try: lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except OSError: return out
    for line in lines:
        line = line.strip()
        if not line: continue
        try: e = json.loads(line)
        except ValueError: continue
        if isinstance(e, dict) and e.get("word") and e.get("op") in ("add", "delete"): out.append(e)
    return out

def apply_events(store, events, log=None):
    """Replay the log onto vocab.json's lookups. Returns (added, dropped, back)."""
    known = {x["id"]: x for x in store.get("lookups", [])}
    added = dropped = back = 0
    for e in events:
        word = str(e["word"]).strip().lower()
        if not word: continue
        wid = f"app:{word}"
        when = parse_iso(e.get("ts"))
        ts = int(when.timestamp() * 1000) if when else 0
        if e["op"] == "add":
            if wid in known:
                x = known[wid]
                if x.pop("dropped", None):
                    x["carded"] = False; back += 1
                    if log: log(f"reader-pull: {wid} is back")
                if e.get("sentence") and (not x.get("usage") or x.get("ts", 0) < ts): x["usage"] = e["sentence"][:300]
                if ts > x.get("ts", 0): x["ts"] = ts
            else:
                x = {"id": wid, "word": word, "stem": word, "usage": (e.get("sentence") or "")[:300],
                     "book": e.get("title") or "unknown", "ts": ts, "source": SOURCE, "review_count": 0, "streak": 0,
                     "highlight": "", "carded": False}
                store.setdefault("lookups", []).append(x); known[wid] = x; added += 1
        else:
            x = known.get(wid)
            if x is not None and not x.get("dropped"):
                x["dropped"] = True; x["carded"] = True; dropped += 1
    return added, dropped, back

def read_decisions(path):
    """cleanup.jsonl → the judgements in file order (app repo docs/CONTRACT.md, "Cleanup"); a broken line is skipped."""
    out = []
    try: lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    except OSError: return out
    for line in lines:
        line = line.strip()
        if not line: continue
        try: e = json.loads(line)
        except ValueError: continue
        if isinstance(e, dict) and e.get("slug") and e.get("target") and e.get("kind") in ("word", "head") and e.get("action") in ("fix", "remove", "keep"):
            out.append(e)
    return out

def apply_decisions(store, events):
    """Latest judgement per slug + kind + target onto cleanup.json: {slug: {"kind:target": {...}}}. Returns how many changed."""
    n = 0
    for e in events:
        per = store.setdefault(e["slug"], {})
        key = f"{e['kind']}:{e['target']}"
        d = {"ts": e.get("ts", ""), "kind": e["kind"], "target": e["target"], "action": e["action"], "fix": (e.get("fix") or "") if e["action"] == "fix" else ""}
        if per.get(key) != d: per[key] = d; n += 1
    return n

def fold_time(daily, files, folded, log=None):
    """time/*.json not yet folded → minutes onto the user's day. Returns the names folded now."""
    new = []
    for f in sorted(files):
        if f.name in folded: continue
        rec = load(f, None)
        if not isinstance(rec, dict): continue
        when = parse_iso(rec.get("started"))
        try: sec = int(rec.get("seconds") or 0)
        except (TypeError, ValueError): sec = 0
        if not when or sec <= 0: continue
        date = local_date(when)
        old = daily.get(date) or {}
        ko = old.get("ko_min", old.get("min", 0.0) if "app_min" not in old else 0.0)
        app = round(old.get("app_min", 0.0) + sec / 60, 1)
        books = list(old.get("books") or [])
        title = rec.get("title") or rec.get("filename")
        if title and title not in books: books.append(title)
        daily[date] = {"min": round(ko + app, 1), "pages": old.get("pages", 0), "books": books, "ko_min": round(ko, 1), "app_min": app}
        new.append(f.name)
    if new and log: log(f"reader-pull: {len(new)} stretch(es) of reading folded")
    return new

def fold_progress(progress, doc, books, passage_for, log=None):
    """The app's positions onto progress.json: through books.json's partial_md5; newer wins."""
    by_md5 = {h: b for b in books for h in (b.get("md5_history") or []) if h}
    by_md5.update({b.get("partial_md5"): b for b in books if b.get("partial_md5")})   # a cleaned EPUB's old hashes still map
    moved = 0
    for md5, p in (doc.get("books") or {}).items():
        b = by_md5.get(md5)
        if not b or not b.get("slug"):
            if md5 and not any(x.get("partial_md5") == md5 for x in books):
                books.append({"slug": None, "title": p.get("title"), "partial_md5": md5, "passages": None, "seen": SOURCE})
            continue
        stamp = p.get("updated") or ""
        cur = progress.get(b["slug"]) or {}
        if cur.get("timestamp") and stamp <= cur["timestamp"]: continue
        pct = p.get("percentage")
        try: pct = round(float(pct), 4)
        except (TypeError, ValueError): continue
        progress[b["slug"]] = {"title": b.get("title") or p.get("title"), "percentage": pct,
                               "passage": passage_for(pct, b.get("passages")), "page": None, "total_pages": None,
                               "chapter": p.get("chapter"), "device": SOURCE, "timestamp": stamp, "source": SOURCE}
        moved += 1
    return moved

def fold_dir(d, vocab, daily, progress, books, state, passage_for, log=None):
    d = pathlib.Path(d)
    added = dropped = back = moved = 0
    if (d / "vocab.jsonl").is_file():
        # Append-only, so only the lines after the last fold are new; a shorter file is a rewritten
        # log (a reinstall) and is replayed from the start — the result is the same, the counts are not.
        events = read_events(d / "vocab.jsonl")
        n = int(state.get("vocab_applied") or 0)
        if n > len(events): n = 0
        added, dropped, back = apply_events(vocab, events[n:], log=log)
        state["vocab_applied"] = len(events)
        vocab["synced"] = dt.date.today().isoformat()
    judged = 0
    if (d / "cleanup.jsonl").is_file():
        events = read_decisions(d / "cleanup.jsonl")
        n = int(state.get("cleanup_applied") or 0)
        if n > len(events): n = 0
        if events[n:]:
            cleanup = load(CLEANUP, {})
            judged = apply_decisions(cleanup, events[n:])
            dump(CLEANUP, cleanup)
        state["cleanup_applied"] = len(events)
    folded = set(state.get("time_folded") or [])
    new = fold_time(daily, list((d / "time").glob("*.json")) if (d / "time").is_dir() else [], folded, log=log)
    state["time_folded"] = sorted(folded | set(new))
    doc = load(d / "progress.json", None)
    if isinstance(doc, dict): moved = fold_progress(progress, doc, books, passage_for, log=log)
    return {"vocab_added": added, "vocab_dropped": dropped, "vocab_back": back, "time_new": len(new), "moved": moved, "judged": judged}

def selftest_cleanup():
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        (d / "cleanup.jsonl").write_text(
            '{"version":1,"ts":"2026-09-23T18:40:12Z","slug":"s","kind":"word","target":"achicve","action":"fix","fix":"achieve"}\n'
            '{"version":1,"ts":"2026-09-23T18:40:40Z","slug":"s","kind":"head","target":"Aclassless society","action":"remove","fix":""}\n'
            'garbage\n'
            '{"version":1,"ts":"2026-09-23T18:41:00Z","slug":"s","kind":"word","target":"achicve","action":"keep","fix":"stale"}\n', encoding="utf-8")
        ev = read_decisions(d / "cleanup.jsonl")
        assert len(ev) == 3, ev
        store = {}
        assert apply_decisions(store, ev) == 3 and store["s"]["word:achicve"]["action"] == "keep" and store["s"]["word:achicve"]["fix"] == "", store
        assert store["s"]["head:Aclassless society"]["action"] == "remove"
        assert apply_decisions(store, ev[-1:]) == 0, "the latest line again changes nothing"
    print("reader-pull cleanup selftest: OK")

def selftest():
    selftest_cleanup()
    ko = _ko()
    with tempfile.TemporaryDirectory() as t:
        d = pathlib.Path(t); (d / "time").mkdir()
        md5 = "bf906459a4b4ca58cf49e66906f9e730"
        (d / "vocab.jsonl").write_text(
            '{"version":1,"ts":"2026-09-22T07:02:51Z","op":"add","word":"Respite","sentence":"No respite for the victor.","title":"The Origins","book_md5":"%s"}\n'
            '{"version":1,"ts":"2026-09-22T07:03:00Z","op":"add","word":"haste","sentence":"In haste.","title":"The Origins","book_md5":"%s"}\n'
            'not json\n'
            '{"version":1,"ts":"2026-09-22T07:40:12Z","op":"delete","word":"respite","title":"The Origins","book_md5":"%s"}\n' % (md5, md5, md5), encoding="utf-8")
        (d / "time" / "20260922T070100Z.json").write_text(json.dumps({"version": 1, "started": "2026-09-22T07:01:00Z", "ended": "2026-09-22T07:19:30Z",
            "seconds": 1110, "book_md5": md5, "title": "The Origins", "from_pct": 0.08, "to_pct": 0.09}), encoding="utf-8")
        (d / "time" / "20260922T230000Z.json").write_text(json.dumps({"started": "2026-09-22T23:30:00Z", "seconds": 600, "title": "The Origins"}), encoding="utf-8")
        (d / "progress.json").write_text(json.dumps({"version": 1, "updated": "2026-09-22T07:19:30Z", "books": {
            md5: {"title": "The Origins", "filename": "x.epub", "percentage": 0.0913, "spine": 7, "fraction": 0.42, "chapter": "Antisemitism", "updated": "2026-09-22T07:19:30Z"},
            "0000": {"title": "Unknown", "percentage": 0.5, "updated": "2026-09-22T07:19:30Z"}}}), encoding="utf-8")
        vocab = {"lookups": [{"id": "ko:haste", "word": "haste", "source": "koreader", "usage": "", "carded": False}]}
        daily = {"2026-09-22": {"min": 4.2, "pages": 3, "books": ["Hannah_Arendt__The_Origins_of_Totalitarianism"]}}
        progress = {"the-origins-of-totalitarianism": {"title": "The Origins of Totalitarianism", "percentage": 0.0826, "passage": "B119", "timestamp": "2026-09-21T09:32:31Z", "source": "statistics"}}
        books = [{"slug": "the-origins-of-totalitarianism", "title": "The Origins of Totalitarianism", "partial_md5": md5, "passages": 1433}]
        state = {}
        s = fold_dir(d, vocab, daily, progress, books, state, ko.passage_for)
        ids = {x["id"]: x for x in vocab["lookups"]}
        assert s["vocab_added"] == 2 and s["vocab_dropped"] == 1, s
        assert ids["app:respite"]["dropped"] and ids["app:respite"]["carded"] and ids["app:respite"]["usage"] == "No respite for the victor.", ids["app:respite"]
        assert ids["app:haste"]["source"] == "app" and not ids["app:haste"].get("dropped") and "ko:haste" in ids, "the app's word sits beside KOReader's, never replaces it"
        # the 07:01 stretch is the 22nd; 23:30 UTC in September is 00:30 the 23rd in London
        assert daily["2026-09-22"] == {"min": 22.7, "pages": 3, "books": ["Hannah_Arendt__The_Origins_of_Totalitarianism", "The Origins"], "ko_min": 4.2, "app_min": 18.5}, daily["2026-09-22"]
        assert daily["2026-09-23"]["app_min"] == 10.0 and daily["2026-09-23"]["min"] == 10.0, daily
        assert sorted(state["time_folded"]) == ["20260922T070100Z.json", "20260922T230000Z.json"]
        p = progress["the-origins-of-totalitarianism"]
        assert p["source"] == "app" and p["passage"] == "B131" and p["chapter"] == "Antisemitism" and p["timestamp"] == "2026-09-22T07:19:30Z", p
        assert any(b.get("partial_md5") == "0000" and b["slug"] is None for b in books), "an unregistered book is listed, never positioned"
        # second run: the log replays to the same state, the stretches are not folded twice, the position does not move back
        s2 = fold_dir(d, vocab, daily, progress, books, state, ko.passage_for)
        assert s2["time_new"] == 0 and s2["vocab_added"] == 0 and s2["vocab_dropped"] == 0 and daily["2026-09-22"]["app_min"] == 18.5, (s2, daily)
        # saved again after the delete: back, and offerable again
        with open(d / "vocab.jsonl", "a", encoding="utf-8") as f:
            f.write('{"ts":"2026-09-23T08:00:00Z","op":"add","word":"respite","sentence":"A respite.","title":"The Origins"}\n')
        s3 = fold_dir(d, vocab, daily, progress, books, state, ko.passage_for)
        assert s3["vocab_back"] == 1 and not ids["app:respite"].get("dropped") and ids["app:respite"]["carded"] is False, ids["app:respite"]
        # a KOReader day folded later keeps the app's minutes (koreader-pull.fold)
        ko_daily = {"2026-09-22": {"min": 5.0, "pages": 4, "books": ["Hannah_Arendt__The_Origins_of_Totalitarianism"]}}
        _v, d2, _p, _b, _s = ko.fold([], ko_daily, {}, {}, vocab={"lookups": []}, daily=dict(daily), progress={}, books=[])
        assert d2["2026-09-22"]["min"] == 23.5 and d2["2026-09-22"]["ko_min"] == 5.0 and d2["2026-09-22"]["app_min"] == 18.5 and "The Origins" in d2["2026-09-22"]["books"], d2["2026-09-22"]
    print("reader-pull selftest: OK"); return 0

def main():
    if "--selftest" in sys.argv: return selftest()
    if "--dir" not in sys.argv: print("reader-pull: --dir <copy of reading/> required (cloud-sync passes it)"); return 2
    d = pathlib.Path(sys.argv[sys.argv.index("--dir") + 1])
    if not d.is_dir(): print(f"reader-pull: {d} is not a folder — skipped"); return 3
    ko = _ko()
    vocab, daily, progress, books, state = load(VOCAB, {"lookups": []}), load(DAILY, {}), load(PROGRESS, {}), load(BOOKS, []), load(STATE, {})
    s = fold_dir(d, vocab, daily, progress, books, state, ko.passage_for, log=print)
    dump(VOCAB, vocab); dump(DAILY, daily); dump(PROGRESS, progress); dump(BOOKS, books); dump(STATE, state)
    pos = "; ".join(f"{p.get('title')} {round((p.get('percentage') or 0) * 100)}% ≈ {p.get('passage')} ({p.get('source')})" for p in progress.values()) or "no position"
    print(f"reader-pull ({d}): +{s['vocab_added']} words, {s['vocab_dropped']} dropped, {s['vocab_back']} back; {s['time_new']} stretch(es) folded; {s['judged']} cleanup judgement(s); {pos}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
