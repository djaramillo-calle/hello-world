#!/usr/bin/env python3
"""srs-deck.py — the flashcard deck the app reviews (app repo docs/CONTRACT.md, "Cards").

    python3 scripts/srs-deck.py               # queue + Anki export → logs/srs/cards.json (promotes ≤25 queued/week)
    python3 scripts/srs-deck.py --migrate     # also replay Anki's review log through FSRS → logs/srs/seed-state.json
    python3 scripts/srs-deck.py --dry-run     # build, change nothing
    python3 scripts/srs-deck.py --selftest

The deck = every card that was live in Anki on the day the app took over (logs/srs/anki-export.json,
written once by anki-export.py) + every queue row with status `added` + up to 25 `queued` rows per
rolling week, promoted here (status → added, note_id → the app card id). Ids: the queue's own
(`c00042`) when the front matches a queue row, else `anki-<note id>`. A card the app has never
reviewed but Anki had carries `state`, the FSRS state obtained by replaying its Anki reviews
(--migrate, py-fsrs in .venv-anki); the app uses it only until its first own review.
The coach stopped pushing to Anki the day the Cards tab shipped (2026-09-23)."""
import datetime as dt, importlib.util, json, os, pathlib, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
EXPORT = REPO / "logs" / "srs" / "anki-export.json"
SEED = REPO / "logs" / "srs" / "seed-state.json"
OUT = REPO / "logs" / "srs" / "cards.json"
VENV = REPO / ".venv-anki"
CAP = 25

def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def load_json(p, default):
    try: return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError): return default

def norm(front): return " ".join((front or "").split()).strip().lower()

def iso(t): return t.strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_iso(s):
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError): return None

def added_last_week(rows, now):
    cutoff = now - dt.timedelta(days=7); n = 0
    for r in rows:
        if r.get("status") != "added": continue
        t = parse_iso(r.get("added_at") or r.get("created"))
        if t and t >= cutoff: n += 1
    return n

def build(rows, export, seed, now, cap=CAP, promote=True):
    """(deck dict, promoted rows). `rows` are mutated: promoted queued rows become added."""
    by_front = {}
    for r in rows:
        if r.get("status") in ("added", "queued"): by_front.setdefault(norm(r.get("front")), r)
    notes = {n["id"]: n for n in export.get("notes", [])}
    cards_by_note = {c["note"]: c for c in export.get("cards", [])}
    deck, seen = [], set()
    def card_for(cid, front, back, tags, added, suspended):
        c = {"id": cid, "front": front, "back": back, "tags": tags, "added": added, "suspended": bool(suspended)}
        st = seed.get(cid)
        if st: c["state"] = st
        return c
    # 1. what Anki had: ids from the queue when the front matches, else anki-<nid>
    for nid, n in sorted(notes.items()):
        ac = cards_by_note.get(nid, {})
        q = by_front.get(norm(n["front"]))
        cid = q["id"] if q else f"anki-{nid}"
        if q and q.get("status") == "queued":      # it was in Anki all along: mark it added, no cap spent
            q["status"] = "added"; q["note_id"] = cid; q["added_at"] = q.get("added_at") or iso(now)
        added = (q.get("created", "")[:10] if q else dt.datetime.fromtimestamp(nid / 1000, dt.timezone.utc).strftime("%Y-%m-%d"))
        deck.append(card_for(cid, n["front"], n["back"], n.get("tags") or [], added, ac.get("queue") == -1)); seen.add(cid)
    # 2. queue rows already added (through Anki earlier, or here before)
    for r in rows:
        if r.get("status") == "added" and r["id"] not in seen:
            deck.append(card_for(r["id"], r["front"], r["back"], (r.get("tags") or "auto").split(), r.get("created", "")[:10], False)); seen.add(r["id"])
    # 3. promote queued rows under the weekly cap, oldest first, dedupe by front
    promoted = []
    if promote:
        room = max(0, cap - added_last_week(rows, now))
        fronts = {norm(c["front"]) for c in deck}
        for r in sorted((r for r in rows if r.get("status") == "queued"), key=lambda r: r.get("created", "")):
            if norm(r.get("front")) in fronts: r["status"] = "skipped"; continue   # a duplicate is settled whatever the cap
            if len(promoted) >= room: continue
            r["status"] = "added"; r["note_id"] = r["id"]; r["added_at"] = iso(now)
            deck.append(card_for(r["id"], r["front"], r["back"], (r.get("tags") or "auto").split(), r.get("created", "")[:10], False))
            fronts.add(norm(r["front"])); promoted.append(r)
    deck.sort(key=lambda c: (c["added"], c["id"]))
    return {"version": 1, "built": iso(now), "cards": deck}, promoted

# ---- migration: Anki's review log → FSRS state, per card ---------------------------------

def ensure_fsrs():
    """Re-exec under .venv-anki with py-fsrs installed when the library is missing."""
    try:
        import fsrs  # noqa: F401
        return
    except ImportError:
        pass
    py = VENV / "bin" / "python"
    if os.environ.get("SRS_DECK_REEXEC"): sys.exit("srs-deck: the fsrs library is still missing inside .venv-anki")
    if not (VENV / "pyvenv.cfg").exists(): subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    subprocess.run([str(py), "-m", "pip", "install", "-q", "fsrs"], check=True)
    os.environ["SRS_DECK_REEXEC"] = "1"
    os.execv(str(py), [str(py)] + sys.argv)

def replay(export, id_of):
    """Each Anki card's reviews through the reference scheduler (fuzz off) → {app card id: SrsCardState}."""
    from fsrs import Scheduler, Card, Rating
    sch = Scheduler(enable_fuzzing=False)
    by_card = {}
    for r in export.get("revlog", []):
        by_card.setdefault(r["card"], []).append(r)
    out = {}
    for ac in export.get("cards", []):
        revs = by_card.get(ac["id"]) or []
        cid = id_of(ac["note"])
        if not cid or not revs: continue
        card = Card(card_id=1)
        lapses = 0
        for r in sorted(revs, key=lambda x: x["ts"]):
            t = parse_iso(r["ts"]); ease = r["ease"] if r["ease"] in (1, 2, 3, 4) else 3
            if ease == 1 and card.state.value == 2: lapses += 1
            card, _ = sch.review_card(card, Rating(ease), t)
        out[cid] = {"state": card.state.value, "step": card.step, "stability": card.stability, "difficulty": card.difficulty,
                    "due": iso(card.due), "last_review": iso(card.last_review), "reps": len(revs), "lapses": lapses}
    return out

def main():
    a = sys.argv[1:]
    if "--selftest" in a: return selftest()
    dry = "--dry-run" in a
    pr = _load("practice-review")
    rows = pr.load_queue()
    export = load_json(EXPORT, {})
    now = dt.datetime.now(dt.timezone.utc)
    if "--migrate" in a:
        ensure_fsrs()
        by_front = {norm(r.get("front")): r["id"] for r in rows if r.get("status") in ("added", "queued")}
        notes = {n["id"]: n for n in export.get("notes", [])}
        def id_of(nid):
            n = notes.get(nid)
            if not n: return None
            return by_front.get(norm(n["front"])) or f"anki-{nid}"
        seed = replay(export, id_of)
        SEED.parent.mkdir(parents=True, exist_ok=True)
        if not dry: SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"srs-deck: replayed Anki's log → {len(seed)} seed state(s) ({sum(1 for s in seed.values() if s['state'] == 2)} in review)")
    seed = load_json(SEED, {})
    deck, promoted = build(rows, export, seed, now, promote=not dry)
    if not dry:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(deck, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        pr.save_queue(rows)
    seeded = sum(1 for c in deck["cards"] if c.get("state"))
    print(f"srs-deck: {len(deck['cards'])} cards ({seeded} with an Anki-derived state, {sum(1 for c in deck['cards'] if c['suspended'])} suspended), "
          f"{len(promoted)} promoted from the queue this run, {sum(1 for r in rows if r.get('status') == 'queued')} still queued"
          + (" [dry run]" if dry else f" → {OUT.relative_to(REPO)}"))
    return 0

def selftest():
    now = dt.datetime(2026, 9, 23, 7, tzinfo=dt.timezone.utc)
    export = {"notes": [{"id": 1789000000000, "front": "Say it: one", "back": "one", "tags": ["auto"]},
                        {"id": 1789300000001, "front": "Say it:  extra   spaces", "back": "two", "tags": []}],
              "cards": [{"id": 5, "note": 1789000000000, "queue": 2}, {"id": 6, "note": 1789300000001, "queue": -1}],
              "revlog": [{"card": 5, "ts": "2026-09-15T07:00:00Z", "ease": 3}]}
    rows = [{"id": "c00001", "created": "2026-09-10T00:00:00Z", "front": "Say it: one", "back": "one", "tags": "auto", "status": "added", "note_id": "123"},
            {"id": "c00002", "created": "2026-09-11T00:00:00Z", "front": "Say it: three", "back": "three", "tags": "", "status": "queued", "note_id": ""},
            {"id": "c00003", "created": "2026-09-12T00:00:00Z", "front": "SAY IT: ONE", "back": "dup", "tags": "", "status": "queued", "note_id": ""},
            {"id": "c00004", "created": "2026-09-12T00:00:00Z", "front": "Say it: four", "back": "four", "tags": "", "status": "queued", "note_id": ""}]
    seed = {"c00001": {"state": 2, "step": None, "stability": 2.3, "difficulty": 4.0, "due": "2026-09-17T07:00:00Z", "last_review": "2026-09-15T07:00:00Z", "reps": 1, "lapses": 0}}
    deck, promoted = build(rows, export, seed, now, cap=1)
    ids = [c["id"] for c in deck["cards"]]
    assert ids == ["c00001", "c00002", "anki-1789300000001"], ids          # sorted by added date, then id
    assert deck["cards"][0]["state"]["stability"] == 2.3 and "state" not in deck["cards"][1], deck["cards"][:2]
    assert deck["cards"][2]["suspended"] is True and deck["cards"][2]["front"] == "Say it:  extra   spaces"
    assert [r["id"] for r in promoted] == ["c00002"] and rows[1]["status"] == "added" and rows[1]["note_id"] == "c00002"
    assert rows[2]["status"] == "skipped", "a queued row whose front is already in the deck is skipped, not added twice"
    assert rows[3]["status"] == "queued", "the cap (1) leaves the fourth queued"
    # the cap counts what was added in the last 7 days
    assert added_last_week(rows, now) == 1 and added_last_week(rows, now + dt.timedelta(days=8)) == 0
    # replay: one Good review → a review-state card with the reference's initial stability
    try:
        import fsrs  # noqa: F401
        st = replay(export, lambda nid: {1789000000000: "c00001"}.get(nid))
        assert st["c00001"]["state"] == 1 and abs(st["c00001"]["stability"] - 2.3065) < 1e-9 and st["c00001"]["reps"] == 1, st
    except ImportError:
        print("srs-deck selftest: (py-fsrs not installed here; replay not exercised)")
    print("srs-deck selftest: OK")

if __name__ == "__main__":
    sys.exit(main())
