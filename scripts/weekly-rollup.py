#!/usr/bin/env python3
"""Weekly training log: roll the week's telemetry into logs/weekly.tsv.

    python3 scripts/weekly-rollup.py                 # current ISO week
    python3 scripts/weekly-rollup.py --week 2026-09-07
    python3 scripts/weekly-rollup.py --set conversations=2 listening_days=5 notes="tutor cancelled Thu -> AI"
    python3 scripts/weekly-rollup.py --selftest

Automatable columns come from repo data (Anki stats, practice logs,
dial-log). Self-report columns (conversations, listening_days, notes) are
set with --set and preserved across re-runs. Idempotent per week_start.
Load is adherence, not ability: nothing here feeds tracking.tsv.
"""
import datetime as dt, json, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
WEEKLY = REPO / "logs" / "weekly.tsv"
ANKI = REPO / "logs" / "anki-stats.json"
PRACTICE = REPO / "logs" / "practice"
DIAL_LOG = REPO / "logs" / "dial-log.tsv"

COLS = ["week_start", "srs_days", "reviews", "recordings", "rec_wpm_mean",
        "rec_filler_pct", "conversations", "listening_days", "dial", "floor_ok", "notes"]
FLOOR = {"conversations": 2, "srs_days": 5, "recordings": 1, "listening_days": 5}

def monday(d):
    return d - dt.timedelta(days=d.weekday())

def load_weekly():
    rows = {}
    if WEEKLY.exists():
        lines = [l.rstrip("\n") for l in WEEKLY.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#")]
        if lines:
            hdr = lines[0].split("\t")
            for l in lines[1:]:
                d = dict(zip(hdr, l.split("\t")))
                rows[d["week_start"]] = d
    return rows

def save_weekly(rows):
    WEEKLY.parent.mkdir(exist_ok=True)
    out = ["# Weekly training log — load/adherence, one row per ISO week (Monday).",
           "# Floors: conversations>=2 (>=1 human) | srs_days>=5 | recordings>=1 | listening_days>=5",
           "# Auto columns from repo data; conversations/listening_days/notes are self-report (--set).",
           "\t".join(COLS)]
    for k in sorted(rows):
        r = rows[k]
        out.append("\t".join(str(r.get(c, "")) for c in COLS))
    WEEKLY.write_text("\n".join(out) + "\n", encoding="utf-8")

def anki_days(week_start, anki_path=ANKI):
    """Days in the week with >=1 review, and total reviews, from the stats export."""
    if not anki_path.exists():
        return "", ""
    d = json.loads(anki_path.read_text(encoding="utf-8"))
    per = d.get("reviews_per_day_since_last_export", {}) or {}
    days, total = 0, 0
    for k, v in per.items():
        try:
            day = dt.date.fromisoformat(k[:10])
        except ValueError:
            continue
        if monday(day) == week_start and v:
            days += 1; total += int(v)
    return days, total

def practice_stats(week_start, practice_dir=PRACTICE):
    if not practice_dir.exists():
        return 0, "", ""
    n, wpms, fill = 0, [], []
    for p in practice_dir.glob("*.json"):
        if p.name.startswith("."):
            continue
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            day = dt.date.fromisoformat(str(r.get("recorded", ""))[:10])
        except Exception:
            continue
        if monday(day) != week_start:
            continue
        n += 1
        if r.get("wpm"): wpms.append(float(r["wpm"]))
        if r.get("words"):
            fill.append(100.0 * float(r.get("fillers", 0)) / float(r["words"]))
    mean = lambda xs: round(sum(xs) / len(xs), 1) if xs else ""
    return n, mean(wpms), mean(fill)

def current_dial(dial_log=DIAL_LOG):
    last = "DEFAULT"
    if dial_log.exists():
        for l in dial_log.read_text(encoding="utf-8").splitlines():
            if l.startswith("#") or not l.strip() or l.startswith("date"):
                continue
            parts = l.split("\t")
            if len(parts) >= 3: last = parts[2]
    return last

def floor_ok(r):
    def num(x):
        try: return float(x)
        except (TypeError, ValueError): return None
    checks = []
    for k, f in FLOOR.items():
        v = num(r.get(k))
        checks.append(None if v is None else v >= f)
    if any(c is False for c in checks): return "no"
    if all(c is True for c in checks): return "yes"
    return "partial"

def rollup(week_start, sets=None, rows=None, anki_path=ANKI, practice_dir=PRACTICE, dial_log=DIAL_LOG):
    rows = load_weekly() if rows is None else rows
    key = week_start.isoformat()
    r = rows.get(key, {"week_start": key})
    days, total = anki_days(week_start, anki_path)
    n, wpm, fill = practice_stats(week_start, practice_dir)
    r.update({"srs_days": days, "reviews": total, "recordings": n,
              "rec_wpm_mean": wpm, "rec_filler_pct": fill, "dial": current_dial(dial_log)})
    for k, v in (sets or {}).items():
        if k in COLS: r[k] = v
    r["floor_ok"] = floor_ok(r)
    rows[key] = r
    return rows, r

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        anki = td / "anki.json"
        anki.write_text(json.dumps({"reviews_per_day_since_last_export": {
            "2026-09-07": 12, "2026-09-08": 9, "2026-09-09": 0, "2026-09-10": 7, "2026-09-11": 11, "2026-09-12": 5}}))
        pr = td / "practice"; pr.mkdir()
        (pr / "2026-09-11-eng-432.json").write_text(json.dumps({"recorded": "2026-09-11 18:20", "wpm": 118.5, "words": 240, "fillers": 12}))
        (pr / "2026-09-02-old.json").write_text(json.dumps({"recorded": "2026-09-02 18:20", "wpm": 90, "words": 100, "fillers": 20}))
        wk = dt.date(2026, 9, 7)
        rows, r = rollup(wk, {"conversations": "2", "listening_days": "5"}, rows={}, anki_path=anki, practice_dir=pr, dial_log=td / "none.tsv")
        assert r["srs_days"] == 5 and r["reviews"] == 44, r
        assert r["recordings"] == 1 and r["rec_wpm_mean"] == 118.5 and r["rec_filler_pct"] == 5.0, r
        assert r["floor_ok"] == "yes", r
        rows, r = rollup(wk, {"conversations": "1"}, rows=rows, anki_path=anki, practice_dir=pr, dial_log=td / "none.tsv")
        assert r["floor_ok"] == "no" and r["listening_days"] == "5", "self-report preserved, floor re-evaluated"
        rows, r = rollup(dt.date(2026, 9, 14), None, rows=rows, anki_path=anki, practice_dir=pr, dial_log=td / "none.tsv")
        assert r["floor_ok"] == "no" and r["srs_days"] == 0, r
    print("weekly-rollup.py selftest: OK")

def main():
    if "--selftest" in sys.argv:
        return selftest()
    args = sys.argv[1:]
    week = monday(dt.date.today())
    sets = {}
    i = 0
    while i < len(args):
        if args[i] == "--week":
            week = monday(dt.date.fromisoformat(args[i + 1])); i += 2
        elif args[i] == "--set":
            i += 1
            while i < len(args) and not args[i].startswith("--"):
                k, _, v = args[i].partition("="); sets[k] = v; i += 1
        else:
            i += 1
    rows, r = rollup(week, sets)
    save_weekly(rows)
    print("\t".join(COLS)); print("\t".join(str(r.get(c, "")) for c in COLS))
    if r["floor_ok"] != "yes":
        missing = [k for k, f in FLOOR.items() if not str(r.get(k)).strip() or float(r.get(k) or 0) < f]
        print(f"floor: {r['floor_ok']} — below/unknown: {', '.join(missing)}")

if __name__ == "__main__":
    main()
