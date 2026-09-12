#!/usr/bin/env python3
"""Export English Runbook deck stats to logs/anki-stats.json (snapshot; git = history).

Needs desktop Anki open with AnkiConnect (port 8765). Run by hand or via
scripts/coach-sync.sh. Reviews-per-day are deck-scoped, counted since the
previous export's timestamp (30-day window on first run).
"""
import datetime, json, pathlib, sys, urllib.request

API = "http://127.0.0.1:8765"
DECK = "English Runbook"
REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "logs" / "anki-stats.json"

def call(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    with urllib.request.urlopen(urllib.request.Request(API, payload), timeout=15) as r:
        out = json.loads(r.read())
    if out.get("error"):
        raise RuntimeError(f"{action}: {out['error']}")
    return out["result"]

def main():
    try:
        call("version")
    except Exception:
        sys.exit("AnkiConnect not reachable — open Anki first (Desktop/Anki.app)")

    since_ms = None
    if OUT.exists():
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        ts = prev.get("exported", "").replace("Z", "+00:00")
        try:
            since_ms = int(datetime.datetime.fromisoformat(ts).timestamp() * 1000)
        except ValueError:
            pass
    if since_ms is None:
        since_ms = int((datetime.datetime.now(datetime.timezone.utc)
                        - datetime.timedelta(days=30)).timestamp() * 1000)

    reviews = call("cardReviews", deck=DECK, startID=since_ms)
    per_day = {}
    for row in reviews:
        day = datetime.datetime.fromtimestamp(row[0] / 1000).date().isoformat()
        per_day[day] = per_day.get(day, 0) + 1

    n = lambda q: len(call("findCards", query=q))
    stats = {
        "exported": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "deck": DECK,
        "counts": {
            "total":     n(f'deck:"{DECK}"'),
            "new":       n(f'deck:"{DECK}" is:new'),
            "young":     n(f'deck:"{DECK}" -is:new prop:ivl<21'),
            "mature":    n(f'deck:"{DECK}" prop:ivl>=21'),
            "suspended": n(f'deck:"{DECK}" is:suspended'),
        },
        "reviews_per_day_since_last_export": dict(sorted(per_day.items())),
        "leech_candidates": [],
    }
    lapsed = call("findCards", query=f'deck:"{DECK}" prop:lapses>=4')
    if lapsed:
        for c in call("cardsInfo", cards=lapsed):
            front = next(iter(c["fields"].values()))["value"]
            stats["leech_candidates"].append(
                {"cardId": c["cardId"], "front": front, "lapses": c["lapses"]})

    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT)
    print(f"anki-stats: {stats['counts']} | reviews since last export: {len(reviews)}"
          f" | leech candidates: {len(stats['leech_candidates'])}")

if __name__ == "__main__":
    main()
