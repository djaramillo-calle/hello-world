#!/usr/bin/env python3
"""Kindle vocabulary → the Hub's `meta/kindle` document.

    python3 scripts/kindle-hub.py [--out <file>]     # writes logs/hub-kindle.json (the document to write_db)
    python3 scripts/kindle-hub.py --selftest

Sources (both optional; whichever exists):
  logs/kindle-vocab.json      Vocabulary Builder lookups pulled from the e-reader over USB
                              (scripts/kindle-vocab.py, run by the Mac's on-mount LaunchAgent)
  logs/kindle-notebook.json   highlights/notes from Kindle's "Export notebook" emails
                              (scripts/kindle-notebook.py, run by the cloud Routine from Gmail)

The document is compact (≤ 80 recent items, counts per book and per week) so the Hub's
Read tab can show "your words" with the sentence each one appeared in — the cue for saying
it aloud. Lookups are harvest, never a metric: nothing here feeds tracking.tsv.
"""
import datetime as dt, json, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
VOCAB = REPO / "logs" / "kindle-vocab.json"
NOTEBOOK = REPO / "logs" / "kindle-notebook.json"
OUT = REPO / "logs" / "hub-kindle.json"
RECENT = 80

def load(p):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}

def when(ts):
    """Kindle stores lookup timestamps in ms since the epoch; notebook exports carry ISO dates."""
    if ts is None: return None
    if isinstance(ts, (int, float)):
        return dt.datetime.fromtimestamp(ts / 1000 if ts > 1e11 else ts, dt.timezone.utc).strftime("%Y-%m-%d")
    return str(ts)[:10]

def build(vocab, notebook, today=None):
    today = today or dt.date.today()
    items = []
    for x in vocab.get("lookups") or []:
        items.append({"kind": "lookup", "word": x.get("word") or x.get("stem"), "stem": x.get("stem"), "usage": (x.get("usage") or "")[:300],
                      "book": x.get("book") or "unknown", "date": when(x.get("ts")), "carded": bool(x.get("carded"))})
    for x in notebook.get("items") or []:
        items.append({"kind": x.get("kind") or "highlight", "word": x.get("word"), "usage": (x.get("text") or "")[:300], "note": (x.get("note") or "")[:200],
                      "book": x.get("book") or "unknown", "date": when(x.get("date")), "carded": bool(x.get("carded"))})
    items.sort(key=lambda i: i.get("date") or "", reverse=True)
    week_ago = (today - dt.timedelta(days=7)).isoformat()
    by_book = {}
    for i in items: by_book[i["book"]] = by_book.get(i["book"], 0) + 1
    doc = {"updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "total": len(items), "lookups": sum(1 for i in items if i["kind"] == "lookup"),
           "this_week": sum(1 for i in items if (i.get("date") or "") >= week_ago),
           "carded": sum(1 for i in items if i["carded"]),
           "books": sorted(({"book": b, "n": n} for b, n in by_book.items()), key=lambda r: -r["n"])[:8],
           "last_sync": {"vocab": vocab.get("synced") or (max((i["date"] or "" for i in items if i["kind"] == "lookup"), default=None)),
                         "notebook": notebook.get("synced")},
           "recent": items[:RECENT]}
    return doc

def selftest():
    vocab = {"lookups": [
        {"id": 1, "word": "vanquished", "stem": "vanquish", "usage": "no peace treaty for the vanquished and no respite for the victor", "book": "The Origins of Totalitarianism", "ts": 1788900000000, "carded": True},
        {"id": 2, "word": "respite", "stem": "respite", "usage": "no respite for the victor", "book": "The Origins of Totalitarianism", "ts": 1788950000000, "carded": False},
        {"id": 3, "word": "old", "stem": "old", "usage": "", "book": "Other", "ts": 1700000000000, "carded": False}]}
    nb = {"synced": "2026-09-10", "items": [{"kind": "highlight", "text": "the hidden mechanics by which all traditional elements", "book": "The Origins of Totalitarianism", "date": "2026-09-09"}]}
    d = build(vocab, nb, today=dt.date(2026, 9, 10))
    assert d["total"] == 4 and d["lookups"] == 3 and d["carded"] == 1, d
    assert d["this_week"] == 3, d["this_week"]                       # the 2023 lookup is old
    assert d["recent"][0]["kind"] == "highlight" or d["recent"][0]["word"] == "respite", d["recent"][:2]
    assert d["books"][0] == {"book": "The Origins of Totalitarianism", "n": 3}, d["books"]
    assert d["recent"][-1]["word"] == "old" and d["recent"][-1]["date"] == "2023-11-14", d["recent"][-1]
    assert build({}, {}, today=dt.date(2026, 9, 10))["total"] == 0
    print("kindle-hub.py selftest: OK")

def main():
    if "--selftest" in sys.argv: return selftest()
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else OUT
    doc = build(load(VOCAB), load(NOTEBOOK))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"kindle-hub: {doc['total']} items ({doc['lookups']} lookups, {doc['this_week']} this week, {doc['carded']} carded) → {out.relative_to(REPO) if out.is_relative_to(REPO) else out}")
    return 0 if doc["total"] else 3   # 3 = nothing to sync

if __name__ == "__main__":
    sys.exit(main())
