#!/usr/bin/env python3
"""The morning check — the language-learning equivalent of "how is my recovery?".

    python3 scripts/daily-readout.py            # today, from everything in git
    python3 scripts/daily-readout.py --date 2026-09-16
    python3 scripts/daily-readout.py --json
    python3 scripts/daily-readout.py --selftest

Reads only committed data (logs/hub, logs/listening, logs/anki-stats.json,
logs/practice, logs/weekly.tsv, logs/dial-log.tsv, tracking.tsv) and prints a
short, mechanical readout: season position, yesterday, week-to-date load vs
floors, streaks, the day's prescription, and flags. The coach (Claude, in chat
or the Friday Routine) adds judgement on top; this script never does. Load is
adherence, not ability — nothing here is a score.
"""
import datetime as dt, json, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
FLOOR = {"conversations": 2, "srs_days": 5, "listening_days": 5, "recordings": 1}
DAYN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
PLAN = {
    0: "06:45 SRS aloud + read the ANCHOR (record: eng read A00) · 13:00 narrow listening 20′ · 17:20 narrow reading + harvest",
    1: "06:45 SRS aloud + 3′ read-aloud (Hub → Read) · 13:00 narrow listening 20′ · 17:20 AI voice conversation (Hub → Talk) 20′ + harvest",
    2: "06:45 SRS aloud + 3′ read-aloud (Hub → Read) · 13:00 narrow listening 20′ · 17:20 read-aloud / shadow sandwich (dial slot)",
    3: "06:45 SRS aloud + 3′ read-aloud (Hub → Read) · 13:00 narrow listening 10′ · 17:20 warm-up ×3 + tutor 30′",
    4: "06:45 SRS aloud + 3′ read-aloud (Hub → Read) · 13:00 narrow listening 15′ · 18:15 recorded 4/3/2 + week close (Hub → Log)",
    5: "rest · optional personal-circle conversation · time-trial Saturdays: Signal Check 09:30",
    6: "rest · optional personal-circle conversation",
}

def load_json(p, default):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError): return default

def read_tsv(p):
    if not p.exists(): return []
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    if not lines: return []
    hdr = lines[0].split("\t")
    return [dict(zip(hdr, l.split("\t"))) for l in lines[1:]]

def monday(d): return d - dt.timedelta(days=d.weekday())

def gather(repo, today):
    hub = load_json(repo / "logs/hub/days.json", {})
    listen = load_json(repo / "logs/listening/daily.json", {})
    anki = load_json(repo / "logs/anki-stats.json", {})
    per_day = anki.get("reviews_per_day_since_last_export", {}) or {}
    practice = {}
    pdir = repo / "logs/practice"
    if pdir.exists():
        for p in pdir.glob("*.json"):
            if p.name.startswith("."): continue
            r = load_json(p, {}); d = str(r.get("recorded", ""))[:10]
            if d: practice.setdefault(d, []).append(r)
    sessions = load_json(repo / "logs/hub/sessions.json", [])
    trials = read_tsv(repo / "tracking.tsv")
    dial_rows = read_tsv(repo / "logs/dial-log.tsv")
    return {"hub": hub, "listen": listen, "per_day": per_day, "anki": anki, "practice": practice, "sessions": sessions,
            "trials": trials, "dial": dial_rows[-1]["dial"] if dial_rows else "DEFAULT"}

def day_load(D, k):
    h = D["hub"].get(k, {}); c = h.get("conversations") or {}
    listen_min = D["listen"][k]["min"] if k in D["listen"] else h.get("listen_min")
    srs = D["per_day"].get(k)
    if srs is None and h.get("srs") is not None: srs = "done" if h["srs"] else 0
    conv = sum(int(c.get(x) or 0) for x in ("ai", "tutor", "circle", "work"))
    return {"listen_min": listen_min, "srs": srs, "conversations": conv, "human": sum(int(c.get(x) or 0) for x in ("tutor", "circle", "work")),
            "recordings": len(D["practice"].get(k, [])) or (1 if h.get("recording") else 0), "talk_min": h.get("talk_min") or 0,
            "logged": bool(h) or k in D["listen"] or k in D["per_day"] or k in D["practice"]}

def week_load(D, mon, upto):
    w = {"conversations": 0, "human": 0, "srs_days": 0, "listening_days": 0, "recordings": 0, "talk_min": 0, "days": 0}
    d = mon
    while d <= upto and d < mon + dt.timedelta(days=7):
        x = day_load(D, d.isoformat())
        w["conversations"] += x["conversations"]; w["human"] += x["human"]
        w["srs_days"] += 1 if x["srs"] else 0
        w["listening_days"] += 1 if (x["listen_min"] or 0) >= 10 else 0
        w["recordings"] += x["recordings"]; w["talk_min"] += x["talk_min"]; w["days"] += 1
        d += dt.timedelta(days=1)
    return w

def season(D, today):
    if not D["trials"]: return None
    b = dt.date.fromisoformat(D["trials"][0]["date"])
    start = b + dt.timedelta(days=(7 - b.weekday()) or 7)
    week = (today - start).days // 7 + 1
    nxt = next((t for t in (5, 10, 12) if t >= week), None)
    return {"start": start, "week": week, "next_trial": nxt, "next_date": start + dt.timedelta(days=(nxt - 1) * 7 + 5) if nxt else None}

def streak(D, today, pred):
    n, d = 0, today - dt.timedelta(days=1)
    while n < 60 and pred(day_load(D, d.isoformat())):
        n += 1; d -= dt.timedelta(days=1)
    return n

def readout(repo=REPO, today=None):
    today = today or dt.date.today()
    D = gather(repo, today)
    s = season(D, today)
    y = day_load(D, (today - dt.timedelta(days=1)).isoformat())
    wk = week_load(D, monday(today), today)
    last = week_load(D, monday(today) - dt.timedelta(days=7), monday(today) - dt.timedelta(days=1))
    flags = []
    zero = streak(D, today, lambda x: not x["logged"])
    if zero >= 2: flags.append(f"{zero} days with no data at all — two zero days is the runbook's red line (an MVD is a full green day)")
    nospeak = streak(D, today, lambda x: x["conversations"] == 0 and x["talk_min"] == 0 and x["recordings"] == 0)
    if nospeak >= 2: flags.append(f"{nospeak} days without speaking beyond SRS — the AI option is mandatory today")
    if last["days"] and last["conversations"] < FLOOR["conversations"] and wk["days"] >= 4 and wk["conversations"] < FLOOR["conversations"]:
        flags.append("second consecutive week heading below the conversation floor — Thursday → 20′ AI is non-negotiable")
    leech = len(D["anki"].get("leech_candidates", []) or [])
    if leech: flags.append(f"{leech} leech candidate(s) in the deck — suspend or reformulate at the next local session")
    if not s: flags.append("PRE-SEASON: no baseline row — the season clock has not started")
    recent = D["sessions"][:3]
    exp = D["anki"].get("exported", "")
    stale = None
    if exp:
        try: stale = (today - dt.date.fromisoformat(exp[:10])).days
        except ValueError: pass
    if stale is not None and stale > 7: flags.append(f"Anki export is {stale} days old — SRS days are coming from check-ins only")
    return {"date": today.isoformat(), "weekday": DAYN[today.weekday()], "season": s, "dial": D["dial"], "yesterday": y, "week": wk,
            "last_week": last, "flags": flags, "plan": PLAN[today.weekday()], "recent_sessions": recent, "floors": FLOOR}

def fmt(R):
    s = R["season"]; out = []
    head = f"{R['weekday']} {R['date']} · " + (f"season week {s['week']}/12, next time trial {s['next_date']}" if s and 1 <= s["week"] <= 12 else "PRE-SEASON") + f" · dial {R['dial']}"
    out.append(head)
    y = R["yesterday"]
    ybits = []
    if y["listen_min"] is not None: ybits.append(f"listening {y['listen_min']}′")
    if y["srs"]: ybits.append(f"SRS {y['srs']}" + ("" if y["srs"] == "done" else " reviews"))
    if y["conversations"]: ybits.append(f"conversations {y['conversations']} ({y['human']} human)")
    if y["talk_min"]: ybits.append(f"AI talk {y['talk_min']}′")
    if y["recordings"]: ybits.append(f"recordings {y['recordings']}")
    out.append("yesterday: " + (" · ".join(ybits) if ybits else "nothing logged"))
    w = R["week"]; F = R["floors"]
    out.append(f"week to date ({w['days']}d): conversations {w['conversations']}/{F['conversations']} ({w['human']} human) · SRS days {w['srs_days']}/{F['srs_days']} · listening days {w['listening_days']}/{F['listening_days']} · recordings {w['recordings']}/{F['recordings']} · AI talk {w['talk_min']}′")
    lw = R["last_week"]
    if lw["days"]: out.append(f"last week: conversations {lw['conversations']} · SRS days {lw['srs_days']} · listening days {lw['listening_days']} · recordings {lw['recordings']}")
    for sess in R["recent_sessions"][:2]:
        h = sess.get("harvest") or {}
        out.append(f"talk {str(sess.get('started', ''))[:10]}: {round((sess.get('duration_s') or 0) / 60)}′, {sess.get('learner_turns')} turns, {sess.get('learner_words')} words, {sess.get('repair_prompts') or 0} repair prompts" + (f" · repeated: {'; '.join(h['repeated'][:3])}" if h.get("repeated") else ""))
    out.append("today: " + R["plan"])
    for f in R["flags"]: out.append("flag: " + f)
    return "\n".join(out)

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        repo = pathlib.Path(td); (repo / "logs/hub").mkdir(parents=True); (repo / "logs/listening").mkdir()
        (repo / "tracking.tsv").write_text("date\tctest_pct\n2026-09-13\t70\n")
        (repo / "logs/hub/days.json").write_text(json.dumps({
            "2026-09-15": {"date": "2026-09-15", "srs": True, "conversations": {"ai": 1}, "talk_min": 20},
            "2026-09-16": {"date": "2026-09-16", "srs": True, "listen_min": 20, "conversations": {}}}))
        (repo / "logs/listening/daily.json").write_text(json.dumps({"2026-09-15": {"min": 22, "episodes": 1}}))
        (repo / "logs/anki-stats.json").write_text(json.dumps({"exported": "2026-09-16T21:40:00Z", "reviews_per_day_since_last_export": {"2026-09-14": 30, "2026-09-15": 28}, "leech_candidates": [{"cardId": 1}]}))
        (repo / "logs/hub/sessions.json").write_text(json.dumps([{"started": "2026-09-15T17:20:00Z", "duration_s": 1200, "learner_turns": 12, "learner_words": 400, "repair_prompts": 2, "harvest": {"repeated": ["article omission"]}}]))
        R = readout(repo, dt.date(2026, 9, 17))
        assert R["season"]["week"] == 1 and R["season"]["next_date"] == dt.date(2026, 10, 17), R["season"]
        assert R["week"] == {"conversations": 1, "human": 0, "srs_days": 3, "listening_days": 2, "recordings": 0, "talk_min": 20, "days": 4}, R["week"]
        assert R["yesterday"]["listen_min"] == 20 and R["yesterday"]["srs"] == "done"
        assert any("leech" in f for f in R["flags"]) and not any("PRE-SEASON" in f for f in R["flags"]), R["flags"]
        txt = fmt(R)
        assert "season week 1/12" in txt and "article omission" in txt and "today: 06:45 SRS" in txt, txt
        R2 = readout(repo, dt.date(2026, 9, 20))
        assert any("days without speaking" in f for f in R2["flags"]), R2["flags"]
    print("daily-readout.py selftest: OK")

def main():
    if "--selftest" in sys.argv: return selftest()
    today = dt.date.fromisoformat(sys.argv[sys.argv.index("--date") + 1]) if "--date" in sys.argv else None
    R = readout(today=today)
    if "--json" in sys.argv:
        print(json.dumps(R, indent=1, default=str))
    else:
        print(fmt(R))

if __name__ == "__main__":
    main()
