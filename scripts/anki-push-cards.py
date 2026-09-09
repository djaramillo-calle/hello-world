#!/usr/bin/env python3
"""Push queued production cards (cards/queue.tsv) into desktop Anki via AnkiConnect.

    python3 scripts/anki-push-cards.py            # needs Anki open with AnkiConnect (port 8765)
    python3 scripts/anki-push-cards.py --dry-run
    python3 scripts/anki-push-cards.py --selftest

Rules (CLAUDE.md, Anki section): deck "English Runbook", Basic model, front = cue said
ALOUD, back = target chunk; at most 25 new cards per rolling 7 days across all sources;
duplicates (same front) are skipped. Rows flip status queued → added with the note id,
so the queue is the audit trail and the run is idempotent.
"""
import datetime as dt, json, pathlib, sys, urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
QUEUE = REPO / "cards" / "queue.tsv"
API = "http://127.0.0.1:8765"
DECK, MODEL, CAP = "English Runbook", "Basic", 25

import importlib.util
_spec = importlib.util.spec_from_file_location("practice_review", pathlib.Path(__file__).resolve().parent / "practice-review.py")
_pr = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_pr)   # sibling script with a hyphen in its name
load_queue, save_queue = _pr.load_queue, _pr.save_queue

def anki_call(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    with urllib.request.urlopen(urllib.request.Request(API, payload), timeout=30) as r:
        out = json.loads(r.read())
    if out.get("error"): raise RuntimeError(f"{action}: {out['error']}")
    return out["result"]

def added_last_week(rows, now):
    cutoff = now - dt.timedelta(days=7); n = 0
    for r in rows:
        if r.get("status") == "added":
            try:
                t = dt.datetime.fromisoformat(str(r.get("added_at") or r.get("created")).replace("Z", "+00:00"))
                if t.tzinfo is None: t = t.replace(tzinfo=dt.timezone.utc)   # naive rows count as UTC instead of crashing the push
                if t >= cutoff: n += 1
            except (ValueError, TypeError): pass
    return n

def deck_added_last_week(call):
    """What Anki itself says was added to the deck in the last 7 days (cards added by hand, by the MCP, or the seed import
    are invisible to queue.tsv). None when AnkiConnect is unreachable."""
    try: return len(call("findNotes", query=f'"deck:{DECK}" added:7') or [])
    except Exception: return None

def push(rows, call, now=None, dry=False):
    now = now or dt.datetime.now(dt.timezone.utc)
    used = added_last_week(rows, now)
    deck_n = deck_added_last_week(call)
    if deck_n is not None: used = max(used, deck_n)   # the cap is on the deck, not on this script's own bookkeeping
    room = max(0, CAP - used)
    todo = [r for r in rows if r.get("status") == "queued"][:room]
    if not todo: return 0, room
    if not dry:
        if DECK not in call("deckNames"): call("createDeck", deck=DECK)
    notes = [{"deckName": DECK, "modelName": MODEL, "fields": {"Front": r["front"], "Back": r["back"]},
              "tags": (r.get("tags") or "auto").split(), "options": {"allowDuplicate": False}} for r in todo]
    if dry:
        for r in todo: print(f"would add: {r['front']} → {r['back']}")
        return len(todo), room
    ok = call("canAddNotes", notes=notes)
    ids = call("addNotes", notes=[n for n, k in zip(notes, ok) if k])
    it = iter(ids); added = 0
    for r, k in zip(todo, ok):
        if k:
            nid = next(it, None)
            if nid: r["status"] = "added"; r["note_id"] = str(nid); r["added_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ"); added += 1
            else: r["status"] = "skipped"
        else:
            r["status"] = "skipped"   # duplicate of an existing note
    return added, room

def selftest():
    calls = []
    def fake(action, **p):
        calls.append(action)
        if action == "deckNames": return ["Default"]
        if action == "canAddNotes": return [True, False, True]
        if action == "addNotes": return [1001, 1002]
        if action == "findNotes": return list(range(24))   # Anki knows one more add than queue.tsv does
        return None
    now = dt.datetime(2026, 9, 15, 21, 40, tzinfo=dt.timezone.utc)
    rows = [{"id": "c1", "created": "2026-09-10T00:00:00Z", "front": "Say it: a", "back": "a", "tags": "auto ai", "status": "queued"},
            {"id": "c2", "created": "2026-09-10T00:00:00Z", "front": "Say it: b", "back": "b", "tags": "auto", "status": "queued"},
            {"id": "c3", "created": "2026-09-10T00:00:00Z", "front": "Say it: c", "back": "c", "tags": "auto", "status": "queued"}]
    rows += [{"id": f"o{i}", "created": "2026-09-12T00:00:00Z", "added_at": "2026-09-12T00:00:00Z", "front": f"old {i}", "back": "x", "status": "added"} for i in range(23)]
    rows.append({"id": "n1", "created": "2026-09-12 00:00:00", "added_at": "2026-09-12 00:00:00", "front": "naive", "back": "x", "status": "added"})   # naive timestamp: must not crash
    assert added_last_week(rows, now) == 24
    added, room = push(rows, fake, now)
    assert room == 1 and added == 1, (added, room)   # deck says 24 this week → room for 1
    assert rows[0]["status"] == "added" and rows[0]["note_id"] == "1001" and rows[1]["status"] == "queued" and rows[2]["status"] == "queued", rows[:3]
    assert "createDeck" in calls
    print("anki-push-cards.py selftest: OK")

def main():
    if "--selftest" in sys.argv: return selftest()
    rows = load_queue()
    if not any(r.get("status") == "queued" for r in rows):
        print("anki-push-cards: queue empty"); return
    dry = "--dry-run" in sys.argv
    if not dry:
        try: anki_call("version")
        except Exception: print("anki-push-cards: AnkiConnect not reachable — cards stay queued"); return
    added, room = push(rows, anki_call, dry=dry)
    if not dry: save_queue(rows)
    print(f"anki-push-cards: added {added} (weekly room was {room}); queued left {sum(1 for r in rows if r.get('status') == 'queued')}")

if __name__ == "__main__":
    main()
