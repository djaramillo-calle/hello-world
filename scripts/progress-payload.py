#!/usr/bin/env python3
"""Build the coach→app progress payload.

    python3 scripts/progress-payload.py [--out logs/progress.json] [--days 120]
    python3 scripts/progress-payload.py --selftest

Stage 0 of the in-app progress section (2026-09-16). The app renders; the coach decides. Every
comparability rule lives here, in Python, where it is tested — never re-implemented in Kotlin.

WHAT IS IN IT AND WHAT IS DELIBERATELY NOT
  * Consistency and load, which are honest today: recorded pages, reading minutes, SRS review days,
    book position, and the weekly floor check that is also the stage-promotion rule.
  * NO read-aloud ability series yet. On 2026-09-16 every stored read was found to have been scored
    against a fraction of what he actually read (commit bcf25aa); the rescore is in progress and
    `pron` separately changed meaning on 2026-09-15 when prosody joined the composite. A chart drawn
    now would show a step that is the repair and a drop that is a definition change. `breaks` names
    both so that whatever draws this can never join a line across them.
  * NO streak. `docs/COACH.md`: "one missed day costs nothing; two in a row is the only red line."
    A day-streak makes one miss cost everything visible. The payload ships counts against the floor
    and the number of consecutive weeks at floor, which is the actual promotion rule.

SHAPE. Daily rows for the last `--days` (default 120, matching the app's own `practice.days`
window) and one row per ISO week for everything, including older weeks. A day row is ~266 bytes, a
week row ~228, so a year is about 100 KB and two years about 200 KB: the whole history ships and
the phone never needs paging. `null` means the sensor had nothing to say that day — never 0, which
would be a claim that he did nothing.

Days are Europe/London, the coach's calendar and the reading sensor's, NOT UTC. The app's own
streak is UTC (`TimeUtil.utcDay`) and that mismatch is a separate bug; this file states its
timezone so the two can be reconciled rather than silently disagreeing.
"""
import argparse, datetime as dt, json, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
LOGS = REPO / "logs"
OUT = LOGS / "progress.json"
DAILY_DAYS = 120

# A recording only counts as a page if it is actually a page. practice-review voids anything under
# 30 words (a 5-word pocket recording scored 99 and counted as a day, 2026-09-13); a floor that can
# be met by a 30-word mumble is not a floor, so the payload's own bar is higher.
MIN_PAGE_WORDS = 150
MIN_SRS_REVIEWS = 10      # one flipped card is not a day of SRS
TZ = "Europe/London"


def load(p, default):
    try: return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError): return default


def read_tsv(p):
    try: lines = [l for l in pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    except OSError: return []
    if not lines: return []
    head = lines[0].split("\t")
    return [dict(zip(head, l.split("\t"))) for l in lines[1:]]


def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def iso_week(day):
    y, w, _ = dt.date.fromisoformat(day).isocalendar()
    return f"{y}-W{w:02d}"


def week_monday(day):
    d = dt.date.fromisoformat(day)
    return (d - dt.timedelta(days=d.weekday())).isoformat()


def reads_by_day(practice_dir):
    """Recorded pages per day, from the practice records. Counts only real pages (MIN_PAGE_WORDS)."""
    out = {}
    d = pathlib.Path(practice_dir)
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        if f.name.endswith(".review.json") or f.name.startswith("."): continue
        r = load(f, {})
        if r.get("kind") != "read" or r.get("void"): continue
        day = (r.get("recorded") or "")[:10]
        words = r.get("words") or 0
        if not day or words < MIN_PAGE_WORDS: continue
        e = out.setdefault(day, {"pages": 0, "min": 0.0, "words": 0})
        e["pages"] += 1
        e["min"] += round((r.get("duration_s") or 0) / 60, 1)
        e["words"] += words
    for e in out.values(): e["min"] = round(e["min"], 1)
    return out


def build(repo=REPO, days=DAILY_DAYS, today=None):
    logs = pathlib.Path(repo) / "logs"
    today = dt.date.fromisoformat(today) if today else dt.date.today()
    pages = reads_by_day(logs / "practice")
    reading = load(logs / "reading" / "daily.json", {})
    srs = (load(logs / "anki-days.json", {}) or {}).get("days") or {}
    listen = load(logs / "listening" / "daily.json", {})
    stage = (load(logs / "stage.json", {}) or {}).get("stage") or 1
    floors = {1: {"pages": 5, "srs_days": 5}}.get(stage, {"pages": 5, "srs_days": 5})

    every = sorted(set(pages) | set(reading) | set(srs) | set(listen))
    first = (today - dt.timedelta(days=days - 1)).isoformat()
    rows = []
    for day in every:
        if day < first: continue
        p, r = pages.get(day), reading.get(day) or {}
        lis = listen.get(day) or {}
        n = srs.get(day)
        row = {
            "d": day,
            "page": {"n": p["pages"], "min": p["min"], "words": p["words"]} if p else None,
            "book": {"min": r.get("min"), "pages": r.get("pages")} if r else None,
            "srs": {"reviews": n} if n else None,
            "listen": {"min": lis.get("min")} if lis else None,
        }
        # A day with nothing in it is not a row. An empty row reads as a day he failed, when it is
        # a day no sensor had anything to say about — which is also true of every day before a
        # sensor existed.
        if any(row[k] for k in ("page", "book", "srs", "listen")): rows.append(row)

    weeks = {}
    for day in every:
        w = weeks.setdefault(iso_week(day), {"w": iso_week(day), "start": week_monday(day),
                                             "page_days": 0, "page_min": 0.0, "book_min": 0.0,
                                             "srs_days": 0, "reviews": 0, "listen_days": 0})
        if day in pages:
            w["page_days"] += 1; w["page_min"] += pages[day]["min"]
        if (reading.get(day) or {}).get("min"): w["book_min"] += reading[day]["min"]
        if (srs.get(day) or 0) >= MIN_SRS_REVIEWS:
            w["srs_days"] += 1; w["reviews"] += srs[day]
        if (listen.get(day) or {}).get("min"): w["listen_days"] += 1
    for w in weeks.values():
        w["page_min"] = round(w["page_min"], 1); w["book_min"] = round(w["book_min"], 1)
        w["floor_ok"] = w["page_days"] >= floors["pages"] and w["srs_days"] >= floors["srs_days"]
    # Same rule for weeks: a week in which nothing was recorded by any sensor is not a failed week.
    ordered = [weeks[k] for k in sorted(weeks)
               if weeks[k]["page_days"] or weeks[k]["book_min"] or weeks[k]["reviews"] or weeks[k]["listen_days"]]

    # Consecutive weeks at floor, counted back from the last COMPLETE week: the promotion rule
    # (three in a row proposes stage 2). The current week is still being lived and never counts.
    complete = [w for w in ordered if w["start"] < week_monday(today.isoformat())]
    run = 0
    for w in reversed(complete):
        if w["floor_ok"]: run += 1
        else: break

    prog = load(logs / "reading" / "progress.json", {})
    book = next(iter(prog.values()), {}) if isinstance(prog, dict) else {}
    pairs = load(logs / "pairs" / "state.json", {})

    return {
        "version": 1,
        "written": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tz": TZ,
        "stage": stage,
        "floors": floors,
        "weeks_at_floor": run,
        "rules": {"min_page_words": MIN_PAGE_WORDS, "min_srs_reviews": MIN_SRS_REVIEWS,
                  "miss": "one missed day costs nothing; two in a row is the red line"},
        "book": {"title": book.get("title"), "pct": book.get("percentage"),
                 "passage": book.get("passage"), "page": book.get("page"),
                 "total_pages": book.get("total_pages")} if book else None,
        "breaks": [
            {"date": "2026-09-15", "series": ["read.pron"],
             "note": "prosody entered PronScore; pron is a different composite across this date"},
            {"date": "2026-09-16", "series": ["read.acc", "read.flu", "read.comp", "read.pros"],
             "note": "scored against the run of chunks actually read, not one chunk; earlier reads "
                     "are being rescored and must not be joined to later ones"},
        ],
        "ability": None,   # deliberately absent until the rescore lands — see the module docstring
        "days": rows,
        "weeks": ordered,
        "pairs": {"sessions": pairs.get("sessions_completed"), "plan_source": pairs.get("plan_source")},
    }


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        repo = pathlib.Path(td); logs = repo / "logs"
        (logs / "practice").mkdir(parents=True); (logs / "reading").mkdir(); (logs / "pairs").mkdir()
        def rec(name, day, words, secs):
            (logs / "practice" / name).write_text(json.dumps(
                {"kind": "read", "recorded": f"{day} 09:00", "words": words, "duration_s": secs}))
        rec("a.json", "2026-09-14", 2446, 1452)
        rec("b.json", "2026-09-15", 1458, 918)
        rec("short.json", "2026-09-16", 40, 30)          # under MIN_PAGE_WORDS: not a page
        (logs / "reading" / "daily.json").write_text(json.dumps({"2026-09-14": {"min": 60.0, "pages": 36}}))
        (logs / "anki-days.json").write_text(json.dumps({"days": {"2026-09-15": 36, "2026-09-16": 3}}))
        (logs / "stage.json").write_text(json.dumps({"stage": 1}))
        (logs / "reading" / "progress.json").write_text(json.dumps({"1": {"title": "T", "percentage": 0.08, "passage": "B115"}}))
        p = build(repo, today="2026-09-16")

        days = {d["d"]: d for d in p["days"]}
        assert days["2026-09-14"]["page"]["n"] == 1 and days["2026-09-14"]["book"]["min"] == 60.0
        assert "2026-09-16" in days and days["2026-09-16"]["page"] is None, "a 40-word recording is not a page"
        assert days["2026-09-15"]["book"] is None, "no reading that day means null, never 0"
        assert days["2026-09-16"]["srs"] == {"reviews": 3}, "the count is kept even below the day bar"
        assert all(any(d[k] for k in ("page", "book", "srs", "listen")) for d in p["days"]), "no empty day rows"
        assert all(w["page_days"] or w["book_min"] or w["reviews"] or w["listen_days"] for w in p["weeks"]), \
            "a week no sensor saw is not a failed week"
        w = {x["w"]: x for x in p["weeks"]}["2026-W38"]
        assert w["page_days"] == 2 and w["srs_days"] == 1, "3 reviews is not an SRS day"
        assert w["reviews"] == 36 and w["floor_ok"] is False
        assert p["weeks_at_floor"] == 0, "the week being lived never counts towards promotion"
        assert p["ability"] is None, "no ability series until the reads are rescored"
        assert [b["date"] for b in p["breaks"]] == ["2026-09-15", "2026-09-16"]
        assert p["tz"] == "Europe/London" and p["book"]["passage"] == "B115"
        assert p["floors"] == {"pages": 5, "srs_days": 5}

        # a full week at floor counts, the current one still does not
        for i, day in enumerate(["2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11"]):
            rec(f"w37-{i}.json", day, 400, 300)
        (logs / "anki-days.json").write_text(json.dumps(
            {"days": {d: 20 for d in ["2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11"]}}))
        p2 = build(repo, today="2026-09-16")
        assert {x["w"]: x for x in p2["weeks"]}["2026-W37"]["floor_ok"] is True
        assert p2["weeks_at_floor"] == 1, "one complete week at floor"

        assert len(json.dumps(build(repo, today="2026-09-16"), separators=(",", ":"))) < 4000
    print("progress-payload.py selftest: OK")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    ap.add_argument("--days", type=int, default=DAILY_DAYS)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return selftest()
    p = build(days=a.days)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(p, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    size = a.out.stat().st_size
    print(f"progress-payload: {len(p['days'])} day(s), {len(p['weeks'])} week(s), "
          f"weeks at floor {p['weeks_at_floor']}, stage {p['stage']} → {a.out.relative_to(REPO)} ({size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
