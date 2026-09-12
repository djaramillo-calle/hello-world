#!/usr/bin/env python3
"""Weekly training log: roll the week's telemetry into logs/weekly.tsv.

    python3 scripts/weekly-rollup.py                 # current ISO week
    python3 scripts/weekly-rollup.py --week 2026-09-07
    python3 scripts/weekly-rollup.py --set conversations=2 human_conversations=1 listening_days=5 notes="tutor cancelled Thu -> AI"
    (set conversations together with human_conversations: a total alone leaves the split unknown and floor_ok "partial")
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
HUB = REPO / "logs" / "hub" / "days.json"            # English Hub check-ins + Talk sessions (scripts/hub-fold.py)
LISTEN = REPO / "logs" / "listening" / "daily.json"  # gpodder pull (scripts/listening-pull.py)
READING = REPO / "logs" / "reading" / "daily.json"   # KOReader statistics (scripts/koreader-pull.py)
PAIRS = REPO / "logs" / "pairs" / "sessions"          # Minimal Pairs app sessions (scripts/pairs-pull.py)

COLS = ["week_start", "srs_days", "reviews", "recordings", "rec_wpm_mean",
        "rec_filler_pct", "conversations", "human_conversations", "listening_days", "reading_min", "talk_min", "pairs_sessions", "pairs_untrained_pct", "dial", "stage", "floor_ok", "notes"]
FLOOR = {"conversations": 2, "srs_days": 5, "recordings": 1, "listening_days": 5}   # stage 3
STAGE_FLOORS = {1: {"srs_days": 5, "recordings": 5}, 2: {"srs_days": 5, "recordings": 5, "conversations": 1, "listening_days": 3}, 3: FLOOR}
STAGE = REPO / "logs" / "stage.json"

def current_stage(path=STAGE):
    try: return max(1, min(3, int(json.loads(path.read_text(encoding="utf-8")).get("stage") or 3)))
    except (OSError, ValueError, TypeError): return 3

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
           "# Floors by stage (logs/stage.json): 1 = srs_days>=5, recordings>=5 · 2 = + conversations>=1, listening_days>=3 · 3 = conversations>=2 (>=1 human), srs_days>=5, recordings>=1, listening_days>=5",
           "# Auto columns from repo data (hub + listening + reading sensors fill conversations/human_conversations/listening_days/reading_min when present); --set overrides in writing.",
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
        # .review.json carries the same "recorded" date as its recording: counting both doubled
        # the week's recorded pages and let stage 1's floor pass on half the real adherence.
        if p.name.startswith(".") or p.name.endswith(".review.json"):
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

def pairs_week(week_start, pairs_dir=PAIRS):
    """Minimal Pairs app: sessions this week and percent correct on UNTRAINED words (the honest probe).
    Load + a formative signal for the ledger; never a score, never tracking.tsv."""
    if not pathlib.Path(pairs_dir).is_dir(): return 0, ""
    n, ut, uc = 0, 0, 0
    for p in sorted(pathlib.Path(pairs_dir).glob("*.json")):
        try:
            s = json.loads(p.read_text(encoding="utf-8")); day = dt.date.fromisoformat(str(s.get("started", ""))[:10])
        except Exception: continue
        if monday(day) != week_start: continue
        n += 1; sm = s.get("summary") or {}
        ut += int(sm.get("untrained_trials") or 0); uc += int(sm.get("untrained_correct") or 0)
    return n, (round(100.0 * uc / ut, 1) if ut else "")

def hub_week(week_start, hub_path=HUB, listen_path=LISTEN, reading_path=READING):
    """Sensor-derived load for the week: conversations (hub check-ins + Talk sessions),
    listening days (gpodder minutes, else hub check-in minutes; >=10' counts), SRS
    check-in days (fallback when no Anki export covers the week), AI talk minutes, reading
    minutes (KOReader statistics, else the check-in's read_min)."""
    def load(p):
        try: return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError): return {}
    hub, listen, reading = load(hub_path), load(listen_path), load(reading_path)
    if not hub and not listen and not reading:
        return None
    out = {"conversations": 0, "human": 0, "listening_days": 0, "srs_checkin_days": 0, "talk_min": 0, "days_logged": 0, "reading_min": 0.0}
    for i in range(7):
        k = (week_start + dt.timedelta(days=i)).isoformat()
        h = hub.get(k) or {}
        if h: out["days_logged"] += 1
        c = h.get("conversations") or {}
        n = sum(int(c.get(x) or 0) for x in ("ai", "tutor", "circle", "work"))
        out["conversations"] += n
        out["human"] += sum(int(c.get(x) or 0) for x in ("tutor", "circle", "work"))
        try: mins = float((listen.get(k) or {}).get("min") if isinstance(listen.get(k), dict) else None) if k in listen else float(h.get("listen_min") or 0)
        except (TypeError, ValueError): mins = 0.0
        if mins >= 10: out["listening_days"] += 1
        if h.get("srs"): out["srs_checkin_days"] += 1
        out["talk_min"] += int(h.get("talk_min") or 0)
        try: rmin = float((reading.get(k) or {}).get("min") or 0) if k in reading else float(h.get("read_min") or 0)
        except (TypeError, ValueError): rmin = 0.0
        out["reading_min"] += rmin
    out["reading_min"] = round(out["reading_min"], 1)
    return out

def current_dial(dial_log=DIAL_LOG):
    last = "DEFAULT"
    if dial_log.exists():
        for l in dial_log.read_text(encoding="utf-8").splitlines():
            if l.startswith("#") or not l.strip() or l.startswith("date"):
                continue
            parts = l.split("\t")
            if len(parts) >= 3: last = parts[2]
    return last

def floor_ok(r, floors=None):
    floors = floors if floors is not None else STAGE_FLOORS[3]
    def num(x):
        try: return float(x)
        except (TypeError, ValueError): return None
    checks = []
    for k, f in floors.items():
        v = num(r.get(k))
        checks.append(None if v is None else v >= f)
    if floors.get("conversations", 0) >= 2:   # stage 3: the conversation floor is 2 with at least one human
        human = num(r.get("human_conversations"))
        conv = num(r.get("conversations"))
        if human is not None: checks.append(human >= 1)
        elif conv is not None and conv >= 2: checks.append(None)   # split unknown: the floor cannot be called met
    if any(c is False for c in checks): return "no"
    if all(c is True for c in checks): return "yes"
    return "partial"

def rollup(week_start, sets=None, rows=None, anki_path=ANKI, practice_dir=PRACTICE, dial_log=DIAL_LOG,
           hub_path=HUB, listen_path=LISTEN, reading_path=READING, stage=None, pairs_dir=PAIRS):
    stage = stage if stage is not None else current_stage()
    rows = load_weekly() if rows is None else rows
    key = week_start.isoformat()
    r = rows.get(key, {"week_start": key})
    days, total = anki_days(week_start, anki_path)
    n, wpm, fill = practice_stats(week_start, practice_dir)
    r.update({"srs_days": days, "reviews": total, "recordings": n,
              "rec_wpm_mean": wpm, "rec_filler_pct": fill, "dial": current_dial(dial_log)})
    r["pairs_sessions"], r["pairs_untrained_pct"] = pairs_week(week_start, pairs_dir)
    hub = hub_week(week_start, hub_path, listen_path, reading_path)
    if hub:
        # sensors replace self-report; --set still wins below (a correction in writing)
        r["conversations"] = hub["conversations"]
        r["listening_days"] = hub["listening_days"]
        r["talk_min"] = hub["talk_min"]
        r["reading_min"] = hub["reading_min"]
        if not days and not total and hub["srs_checkin_days"]:
            r["srs_days"] = hub["srs_checkin_days"]   # check-in fallback: no Anki export covers this week
        r["human_conversations"] = hub["human"]
    for k, v in (sets or {}).items():
        if k in COLS: r[k] = v
    if "conversations" in (sets or {}) and "human_conversations" not in (sets or {}):
        r["human_conversations"] = ""   # a self-reported total says nothing about the human/AI split: unknown, not zero
    r["stage"] = stage
    r["floor_ok"] = floor_ok(r, STAGE_FLOORS[stage])
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
        # hermetic: point hub/listen at nonexistent temp files so the selftest never
        # reads the live repo logs/hub or logs/listening (which a real pull may create)
        nohub, nolisten, noread = td / "nohub.json", td / "nolisten.json", td / "noread.json"
        rows, r = rollup(wk, {"conversations": "2", "listening_days": "5"}, rows={}, anki_path=anki, practice_dir=pr, dial_log=td / "none.tsv", hub_path=nohub, listen_path=nolisten, reading_path=noread, stage=3)
        assert r["srs_days"] == 5 and r["reviews"] == 44, r
        assert r["recordings"] == 1 and r["rec_wpm_mean"] == 118.5 and r["rec_filler_pct"] == 5.0, r
        assert r["floor_ok"] == "partial" and r["human_conversations"] == "", "a total without the human split cannot meet the floor: %r" % r
        rows, r = rollup(wk, {"human_conversations": "1"}, rows=rows, anki_path=anki, practice_dir=pr, dial_log=td / "none.tsv", hub_path=nohub, listen_path=nolisten, reading_path=noread, stage=3)
        assert r["floor_ok"] == "yes", r
        rows, r = rollup(wk, {"conversations": "1"}, rows=rows, anki_path=anki, practice_dir=pr, dial_log=td / "none.tsv", hub_path=nohub, listen_path=nolisten, reading_path=noread, stage=3)
        assert r["floor_ok"] == "no" and r["listening_days"] == "5", "self-report preserved, floor re-evaluated"
        rows, r = rollup(dt.date(2026, 9, 14), None, rows=rows, anki_path=anki, practice_dir=pr, dial_log=td / "none.tsv", hub_path=nohub, listen_path=nolisten, reading_path=noread, stage=3)
        assert r["floor_ok"] == "no" and r["srs_days"] == 0, r
        # hub sensors fill the self-report columns; --set still overrides
        hub = td / "days.json"; listen = td / "daily.json"
        hub.write_text(json.dumps({
            "2026-09-14": {"date": "2026-09-14", "listen_min": 20, "srs": True, "conversations": {"ai": 1}, "talk_min": 21},
            "2026-09-15": {"date": "2026-09-15", "listen_min": 5, "srs": True, "conversations": {"tutor": 1}},
            "2026-09-16": {"date": "2026-09-16", "srs": True, "conversations": {}}}))
        listen.write_text(json.dumps({"2026-09-15": {"min": 25, "episodes": 1}, "2026-09-17": {"min": 12, "episodes": 1}}))
        rows, r = rollup(dt.date(2026, 9, 14), None, rows=rows, anki_path=anki, practice_dir=pr, dial_log=td / "none.tsv", hub_path=hub, listen_path=listen, reading_path=noread, stage=3)
        assert r["conversations"] == 2 and r["human_conversations"] == 1 and r["listening_days"] == 3 and r["talk_min"] == 21, r
        assert r["reading_min"] == 0, r   # no reading sensor and no check-in: zero (reading has no floor)
        hub.write_text(json.dumps({"2026-09-14": {"date": "2026-09-14", "listen_min": 20, "srs": True, "conversations": {"ai": 2}}}))
        rows2, r2 = rollup(dt.date(2026, 9, 14), {"listening_days": "5", "srs_days": "5"}, rows={}, anki_path=anki, practice_dir=pr, dial_log=td / "none.tsv", hub_path=hub, listen_path=listen, reading_path=noread, stage=3)
        assert r2["conversations"] == 2 and r2["human_conversations"] == 0 and r2["floor_ok"] == "no", "two AI conversations do not meet the >=1 human floor: %r" % r2
        hub.write_text(json.dumps({
            "2026-09-14": {"date": "2026-09-14", "listen_min": 20, "srs": True, "conversations": {"ai": 1}, "talk_min": 21},
            "2026-09-15": {"date": "2026-09-15", "listen_min": 5, "srs": True, "conversations": {"tutor": 1}},
            "2026-09-16": {"date": "2026-09-16", "srs": True, "conversations": {}}}))
        assert r["srs_days"] == 3, "check-in fallback when the Anki export has nothing for the week: %r" % r
        reading = td / "reading.json"; reading.write_text(json.dumps({"2026-09-14": {"min": 12.5, "pages": 20}, "2026-09-16": {"min": 30}, "2026-09-21": {"min": 99}}))
        hub.write_text(json.dumps({"2026-09-15": {"date": "2026-09-15", "read_min": 10, "conversations": {"tutor": 1}}}))
        rows, r = rollup(dt.date(2026, 9, 14), None, rows=rows, anki_path=anki, practice_dir=pr, dial_log=td / "none.tsv", hub_path=hub, listen_path=listen, reading_path=reading, stage=3)
        assert r["reading_min"] == 52.5, "sensor days + the check-in on a day the sensor has nothing; next week's day excluded: %r" % r
        hub.write_text(json.dumps({
            "2026-09-14": {"date": "2026-09-14", "listen_min": 20, "srs": True, "conversations": {"ai": 1}, "talk_min": 21},
            "2026-09-15": {"date": "2026-09-15", "listen_min": 5, "srs": True, "conversations": {"tutor": 1}},
            "2026-09-16": {"date": "2026-09-16", "srs": True, "conversations": {}}}))
        rows, r = rollup(dt.date(2026, 9, 14), {"conversations": "3"}, rows=rows, anki_path=anki, practice_dir=pr, dial_log=td / "none.tsv", hub_path=hub, listen_path=listen, reading_path=noread, stage=3)
        assert r["conversations"] == "3" and r["human_conversations"] == "" and r["floor_ok"] != "yes", "--set overrides sensors; the split becomes unknown: %r" % r
        rows, r = rollup(dt.date(2026, 9, 14), {"conversations": "3", "human_conversations": "2"}, rows=rows, anki_path=anki, practice_dir=pr, dial_log=td / "none.tsv", hub_path=hub, listen_path=listen, reading_path=noread, stage=3)
        assert r["human_conversations"] == "2", "the split set in writing wins over the sensors: %r" % r
        # stage 1: only SRS days and recorded pages count; a week with 5 of each meets the floor with no conversations at all
        pr1 = td / "p1"; pr1.mkdir()
        for d in range(5): (pr1 / f"2026-09-2{1+d}-eng-read.json").write_text(json.dumps({"recorded": f"2026-09-2{1+d} 06:50", "wpm": 100, "words": 150, "fillers": 2}))
        anki.write_text(json.dumps({"reviews_per_day_since_last_export": {f"2026-09-2{1+d}": 10 for d in range(5)}}))
        rows, r = rollup(dt.date(2026, 9, 21), None, rows={}, anki_path=anki, practice_dir=pr1, dial_log=td / "none.tsv", hub_path=nohub, listen_path=nolisten, reading_path=noread, stage=1)
        assert r["stage"] == 1 and r["recordings"] == 5 and r["srs_days"] == 5 and r["floor_ok"] == "yes", r
        assert floor_ok({"srs_days": 5, "recordings": 4}, STAGE_FLOORS[1]) == "no" and floor_ok({"srs_days": 5, "recordings": 5, "conversations": 0}, STAGE_FLOORS[2]) == "no"
        # a recording and its .review.json are ONE recorded page, not two
        pr2 = td / "practice2"; pr2.mkdir()
        (pr2 / "r1.json").write_text(json.dumps({"recorded": "2026-09-08 07:00", "wpm": 80, "words": 100, "fillers": 0}))
        (pr2 / "r1.review.json").write_text(json.dumps({"recorded": "2026-09-08 07:00", "fluency": {"wpm": 80}}))
        n2, wpm2, _ = practice_stats(dt.date(2026, 9, 7), pr2)
        assert n2 == 1 and wpm2 == 80.0, (n2, wpm2)
        assert current_stage(td / "missing.json") == 3
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
        missing = [k for k, f in STAGE_FLOORS[r["stage"]].items() if not str(r.get(k)).strip() or float(r.get(k) or 0) < f]
        print(f"floor: {r['floor_ok']} — below/unknown: {', '.join(missing)}")

if __name__ == "__main__":
    main()
