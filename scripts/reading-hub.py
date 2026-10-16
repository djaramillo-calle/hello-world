#!/usr/bin/env python3
"""Reading sensors → the Hub's `meta/reading` document.

    python3 scripts/reading-hub.py [--out <file>]     # writes logs/hub-reading.json (the document to write_db)
    python3 scripts/reading-hub.py --selftest

Sources (all optional; whichever exists, all under logs/reading/ — see scripts/koreader-pull.py):
  vocab.json      dictionary lookups with the sentence each appeared in (KOReader on the phone; the Kindle
                  USB bridge writes the same file)
  daily.json      reading minutes per day from KOReader's statistics
  progress.json   position in each book (kosync, else statistics) → the passage the Read tab should offer
  ../kindle-notebook.json   highlights from Kindle "Export notebook" emails, if that channel is ever used

The document is compact (≤ 80 recent words, counts per book and per week) so the Read tab can show
"your words" with their sentences — the cue for saying them aloud — plus this week's reading minutes and
where you are in the book. Lookups are harvest, minutes are load, the position is a pointer: nothing here
feeds tracking.tsv.
"""
import datetime as dt, json, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
RDIR = REPO / "logs" / "reading"
VOCAB, DAILY, PROGRESS = RDIR / "vocab.json", RDIR / "daily.json", RDIR / "progress.json"
LEGACY_VOCAB = REPO / "logs" / "kindle-vocab.json"
NOTEBOOK = REPO / "logs" / "kindle-notebook.json"
OUT = REPO / "logs" / "hub-reading.json"
RECENT = 80

def load(p):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}

def when(ts):
    """Lookup timestamps are ms since the epoch (Kindle) or s×1000 (KOReader); notebook exports carry ISO dates."""
    if ts is None: return None
    if isinstance(ts, (int, float)):
        return dt.datetime.fromtimestamp(ts / 1000 if ts > 1e11 else ts, dt.timezone.utc).strftime("%Y-%m-%d")
    return str(ts)[:10]

def build(vocab, notebook, daily=None, progress=None, today=None):
    today = today or dt.date.today()
    daily, progress = daily or {}, progress or {}
    items = []
    for x in vocab.get("lookups") or []:
        items.append({"kind": "lookup", "word": x.get("word") or x.get("stem"), "stem": x.get("stem"), "usage": (x.get("usage") or "")[:300],
                      "book": x.get("book") or "unknown", "date": when(x.get("ts")), "carded": bool(x.get("carded")),
                      "source": x.get("source") or "kindle"})
    for x in notebook.get("items") or []:
        items.append({"kind": x.get("kind") or "highlight", "word": x.get("word"), "usage": (x.get("text") or "")[:300], "note": (x.get("note") or "")[:200],
                      "book": x.get("book") or "unknown", "date": when(x.get("date")), "carded": bool(x.get("carded")), "source": "notebook"})
    items.sort(key=lambda i: i.get("date") or "", reverse=True)
    week_ago = (today - dt.timedelta(days=7)).isoformat()
    monday = (today - dt.timedelta(days=today.weekday())).isoformat()
    by_book = {}
    for i in items: by_book[i["book"]] = by_book.get(i["book"], 0) + 1
    wk = {k: v for k, v in daily.items() if k >= monday}
    yday = (today - dt.timedelta(days=1)).isoformat()
    reading = {"week_min": round(sum(float(v.get("min") or 0) for v in wk.values()), 1),
               "week_days": sum(1 for v in wk.values() if float(v.get("min") or 0) >= 5),
               "yesterday_min": float((daily.get(yday) or {}).get("min") or 0),
               "today_min": float((daily.get(today.isoformat()) or {}).get("min") or 0),
               "last_day": max(daily) if daily else None,
               "last_14": [{"date": k, "min": daily[k].get("min")} for k in sorted(daily)[-14:]]}
    latest = max(progress.values(), key=lambda p: p.get("timestamp") or "", default=None)
    doc = {"updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "total": len(items), "lookups": sum(1 for i in items if i["kind"] == "lookup"),
           "this_week": sum(1 for i in items if (i.get("date") or "") >= week_ago),
           "carded": sum(1 for i in items if i["carded"]),
           "books": sorted(({"book": b, "n": n} for b, n in by_book.items()), key=lambda r: -r["n"])[:8],
           "last_sync": {"vocab": vocab.get("synced") or (max((i["date"] or "" for i in items if i["kind"] == "lookup"), default=None)),
                         "notebook": notebook.get("synced"), "reading": reading["last_day"]},
           "reading": reading,
           "progress": latest,
           "recent": items[:RECENT]}
    return doc

def selftest():
    vocab = {"lookups": [
        {"id": 1, "word": "vanquished", "stem": "vanquish", "usage": "no peace treaty for the vanquished and no respite for the victor", "book": "The Origins of Totalitarianism", "ts": 1788900000000, "carded": True},
        {"id": "ko:respite", "word": "respite", "stem": "respite", "usage": "no respite for the victor", "book": "The Origins of Totalitarianism", "ts": 1788950000000, "carded": False, "source": "koreader"},
        {"id": 3, "word": "old", "stem": "old", "usage": "", "book": "Other", "ts": 1700000000000, "carded": False}]}
    nb = {"synced": "2026-09-10", "items": [{"kind": "highlight", "text": "the hidden mechanics by which all traditional elements", "book": "The Origins of Totalitarianism", "date": "2026-09-09"}]}
    daily = {"2026-09-04": {"min": 30}, "2026-09-07": {"min": 12.5, "pages": 20}, "2026-09-09": {"min": 4, "pages": 5}}
    prog = {"the-origins-of-totalitarianism": {"title": "The Origins of Totalitarianism", "percentage": 0.12, "passage": "B172", "timestamp": "2026-09-09T20:00:00Z", "source": "kosync"},
            "other": {"title": "Other", "percentage": 0.5, "passage": None, "timestamp": "2026-09-01T20:00:00Z", "source": "statistics"}}
    d = build(vocab, nb, daily, prog, today=dt.date(2026, 9, 10))
    assert d["total"] == 4 and d["lookups"] == 3 and d["carded"] == 1, d
    assert d["this_week"] == 3, d["this_week"]                       # the 2023 lookup is old
    assert d["recent"][0]["kind"] == "highlight" or d["recent"][0]["word"] == "respite", d["recent"][:2]
    assert d["books"][0] == {"book": "The Origins of Totalitarianism", "n": 3}, d["books"]
    assert d["recent"][-1]["word"] == "old" and d["recent"][-1]["date"] == "2023-11-14", d["recent"][-1]
    assert d["reading"]["week_min"] == 16.5 and d["reading"]["week_days"] == 1 and d["reading"]["yesterday_min"] == 4, d["reading"]   # Mon 7th + Wed 9th this week; the 4th is last week; 4' < 5' is not a reading day
    assert d["progress"]["passage"] == "B172" and d["last_sync"]["reading"] == "2026-09-09", d["progress"]
    e = build({}, {}, today=dt.date(2026, 9, 10))
    assert e["total"] == 0 and e["progress"] is None and e["reading"]["week_min"] == 0
    print("reading-hub.py selftest: OK")

def main():
    if "--selftest" in sys.argv: return selftest()
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else OUT
    vocab = load(VOCAB) or load(LEGACY_VOCAB)
    doc = build(vocab, load(NOTEBOOK), load(DAILY), load(PROGRESS))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    r, p = doc["reading"], doc["progress"]
    print(f"reading-hub: {doc['total']} words ({doc['this_week']} this week, {doc['carded']} carded) · reading {r['week_min']}′ on {r['week_days']} days this week · "
          + (f"{p.get('title')} {round((p.get('percentage') or 0) * 100)}% ≈ {p.get('passage')}" if p else "no position") + f" → {out.relative_to(REPO) if out.is_relative_to(REPO) else out}")
    return 0 if (doc["total"] or r["last_day"] or p) else 3   # 3 = nothing to sync

if __name__ == "__main__":
    sys.exit(main())
