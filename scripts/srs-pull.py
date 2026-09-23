#!/usr/bin/env python3
"""srs-pull.py — fold the app's flashcard files into the coach (app repo docs/CONTRACT.md, "Cards").

    python3 scripts/srs-pull.py --dir <folder with revlog.jsonl and/or state.json>
    python3 scripts/srs-pull.py --selftest

`revlog.jsonl` lines are appended to logs/srs/revlog.jsonl (deduped on ts+card+rating),
`state.json` is copied to logs/srs/state.json, and logs/anki-stats.json is rewritten in the
shape the weekly rollup, the readout and the Friday review already read (counts, reviews per
day, seconds per day, leech candidates) with `source: "app (srs-pull.py)"`; logs/anki-days.json
keeps the permanent per-day count. Load and harvest, never a score."""
import datetime as dt, importlib.util, json, pathlib, sys, zoneinfo

REPO = pathlib.Path(__file__).resolve().parent.parent
LOG = REPO / "logs" / "srs" / "revlog.jsonl"
STATE = REPO / "logs" / "srs" / "state.json"
DECK = REPO / "logs" / "srs" / "cards.json"
STATS = REPO / "logs" / "anki-stats.json"
DAYS = REPO / "logs" / "anki-days.json"
TZ = zoneinfo.ZoneInfo("Europe/London")
MATURE_DAYS = 21

def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def load_json(p, default):
    try: return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError): return default

def read_lines(p):
    out = []
    try:
        for line in pathlib.Path(p).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line: continue
            try: out.append(json.loads(line))
            except ValueError: continue
    except OSError: pass
    return out

def parse_iso(s):
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError): return None

def fold_log(new, log_path=LOG):
    """Append unseen reviews; returns (all rows, number added)."""
    have = read_lines(log_path)
    keys = {(r.get("ts"), r.get("card"), r.get("rating")) for r in have}
    added = []
    for r in new:
        k = (r.get("ts"), r.get("card"), r.get("rating"))
        if k in keys or not r.get("ts") or not r.get("card"): continue
        keys.add(k); added.append(r)
    if added:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            for r in added: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return have + added, len(added)

def stats(rows, state, deck, exported=None, days=90):
    """logs/anki-stats.json in the shape anki-revlog.py produced, from the app's files."""
    cards = {c["id"]: c for c in deck.get("cards", [])}
    st = state.get("cards", {})
    counts = {"total": len(cards), "new": 0, "young": 0, "mature": 0, "suspended": 0, "learning": 0}
    for cid, c in cards.items():
        if c.get("suspended"): counts["suspended"] += 1; continue
        s = st.get(cid) or c.get("state")
        if not s: counts["new"] += 1; continue
        if s.get("state") != 2: counts["learning"] += 1; continue
        due, last = parse_iso(s.get("due")), parse_iso(s.get("last_review"))
        ivl = (due - last).days if due and last else 0
        counts["mature" if ivl >= MATURE_DAYS else "young"] += 1
    per, secs = {}, {}
    for r in rows:
        t = parse_iso(r.get("ts"))
        if not t: continue
        day = t.astimezone(TZ).strftime("%Y-%m-%d")
        per[day] = per.get(day, 0) + 1
        secs[day] = secs.get(day, 0) + int((r.get("duration_ms") or 0) / 1000)
    keep = sorted(per)[-days:]
    leeches = [{"cardId": cid, "front": (cards.get(cid) or {}).get("front", "")[:120], "lapses": s.get("lapses", 0)}
               for cid, s in st.items() if (s.get("lapses") or 0) >= 4]
    leeches.sort(key=lambda x: -x["lapses"])
    return {"exported": exported or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "deck": "English Runbook",
            "source": "app (srs-pull.py)", "counts": counts,
            "reviews_per_day_since_last_export": {d: per[d] for d in keep},
            "review_seconds_per_day": {d: secs.get(d, 0) for d in keep},
            "retention_per_day": {}, "leech_candidates": leeches}

def pull(src, log_path=LOG, state_path=STATE, deck_path=DECK, stats_path=STATS, days_path=DAYS, log=print):
    src = pathlib.Path(src)
    new = read_lines(src / "revlog.jsonl") if (src / "revlog.jsonl").is_file() else []
    rows, added = fold_log(new, log_path)
    if (src / "state.json").is_file():
        state = load_json(src / "state.json", None)
        if isinstance(state, dict) and "cards" in state:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    state = load_json(state_path, {})
    s = stats(rows, state, load_json(deck_path, {}))
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = stats_path.with_suffix(".json.tmp"); tmp.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8"); tmp.replace(stats_path)
    _load("anki-cloud").fold_days(s["reviews_per_day_since_last_export"], days_path)
    c = s["counts"]
    log(f"srs-pull: +{added} review(s) ({len(rows)} in the log) · {c['total']} cards: {c['new']} new, {c['learning']} learning, {c['young']} young, {c['mature']} mature, {c['suspended']} suspended · {len(s['leech_candidates'])} leech candidate(s)")
    return added

def main():
    a = sys.argv[1:]
    if "--selftest" in a: return selftest()
    if "--dir" not in a: print(__doc__); return 2
    pull(a[a.index("--dir") + 1])
    return 0

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td); src = td / "srs"; src.mkdir()
        deck = {"cards": [{"id": "a", "front": "Say it: a"}, {"id": "b", "front": "Say it: b"}, {"id": "c", "front": "c"}, {"id": "s", "front": "s", "suspended": True},
                          {"id": "m", "front": "m", "state": {"state": 2, "due": "2026-10-20T00:00:00Z", "last_review": "2026-09-20T00:00:00Z"}}]}
        (td / "cards.json").write_text(json.dumps(deck))
        (src / "revlog.jsonl").write_text("\n".join([
            json.dumps({"ts": "2026-09-23T18:04:11Z", "card": "a", "rating": 3, "duration_ms": 4000}),
            json.dumps({"ts": "2026-09-23T23:30:00Z", "card": "b", "rating": 1, "duration_ms": 2000}),   # 00:30 BST on the 24th
            "not json", ""]) + "\n")
        (src / "state.json").write_text(json.dumps({"version": 1, "cards": {
            "a": {"state": 2, "due": "2026-09-26T00:00:00Z", "last_review": "2026-09-23T18:04:11Z", "lapses": 0},
            "b": {"state": 3, "due": "2026-09-23T23:40:00Z", "last_review": "2026-09-23T23:30:00Z", "lapses": 5}}}))
        logs = []
        n = pull(src, log_path=td / "revlog.jsonl", state_path=td / "state.json", deck_path=td / "cards.json", stats_path=td / "stats.json", days_path=td / "days.json", log=logs.append)
        assert n == 2, n
        s = json.loads((td / "stats.json").read_text())
        assert s["counts"] == {"total": 5, "new": 1, "young": 1, "mature": 1, "suspended": 1, "learning": 1}, s["counts"]
        assert s["reviews_per_day_since_last_export"] == {"2026-09-23": 1, "2026-09-24": 1}, s["reviews_per_day_since_last_export"]
        assert s["review_seconds_per_day"] == {"2026-09-23": 4, "2026-09-24": 2}
        assert s["leech_candidates"] == [{"cardId": "b", "front": "Say it: b", "lapses": 5}], s["leech_candidates"]
        assert s["source"].startswith("app")
        # a second pull of the same file adds nothing and keeps the counts
        assert pull(src, log_path=td / "revlog.jsonl", state_path=td / "state.json", deck_path=td / "cards.json", stats_path=td / "stats.json", days_path=td / "days.json", log=logs.append) == 0
        assert len([l for l in (td / "revlog.jsonl").read_text().splitlines() if l.strip()]) == 2
        assert json.loads((td / "days.json").read_text())["days"].get("2026-09-24") == 1
    print("srs-pull selftest: OK")

if __name__ == "__main__":
    sys.exit(main())
