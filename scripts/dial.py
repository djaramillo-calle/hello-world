#!/usr/bin/env python3
"""Mechanical focus-dial recommendation from tracking.tsv.

    python3 scripts/dial.py            # human-readable recommendation
    python3 scripts/dial.py --json     # machine-readable
    python3 scripts/dial.py --selftest # exercise the rules on synthetic data

Implements docs/TARGET.md "Adjustment protocol" and the profile -> dial
mapping in docs/plan/final-plan.md. It never edits anything; the Friday
review logs its output to logs/dial-log.tsv and a human may override —
in writing, next to the recommendation.

States: PRE-SEASON (no row) · BASELINE (row 1) · TIME-TRIAL (a cycle close ≥ 4 weeks
after the previous one) · MEASUREMENT (a row closer than that, e.g. the week-12 race
row: scored, no lever) · INCOMPLETE (target metric blank: hold) · MANUAL (dial is
DECODE, which only the authentic-audio check can judge). Low dictation is a flag,
never a mechanical DECODE.
"""
import csv, json, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TRACKING = REPO / "tracking.tsv"
DIAL_LOG = REPO / "logs" / "dial-log.tsv"

# Noise thresholds (docs/METHOD.md) — movement at or above = signal
NOISE = {"ctest_pct": 8, "vocab_size": 1100, "dict_pct": 10, "wpm": 12, "mtld": 8, "evidence_n": 3}   # evidence_n: docs/TARGET.md and build-progress.py use +3
# Which metric each dial position is accountable for
# DECODE has no target metric in tracking.tsv: final-plan.md defines it by the dictation speed
# ceiling (< 1.2×) or the authentic-audio check (< 85%), neither of which the battery exports.
# dict_pct is an inflated upper bound (METHOD.md). DECODE is therefore never set mechanically —
# it is a human override, judged on the monthly authentic-audio check, written in the reason column.
TARGET_METRIC = {"DEFAULT": "wpm", "DECODE": None, "AUTOMATIZE": "wpm",
                 "RANGE": "mtld", "USE": "evidence_n"}
PRIORITY = ["DECODE", "AUTOMATIZE", "RANGE", "USE"]
CYCLE_MIN_DAYS = 28   # rows closer than this to the previous kept row are measurements (the week-12 race row), never cycle closes

def read_rows(path=TRACKING):
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            rows.append(line.rstrip("\n").split("\t"))
    if not rows:
        return []
    header, body = rows[0], rows[1:]
    out = []
    for r in body:
        d = dict(zip(header, r))
        for k in list(d):
            if k == "date":
                continue
            try:
                d[k] = float(d[k]) if d[k] != "" else None
            except ValueError:
                d[k] = None
        out.append(d)
    return out

def profiles(row):
    """Return the applicable profiles for one tracking row, in priority order.
    Thresholds mirror diagnostic.html's confidence bands and diagnose()."""
    g = lambda k: row.get(k)
    found = []
    dict_p, ctest, wpm = g("dict_pct"), g("ctest_pct"), g("wpm")
    vocab, beyond, mtld, ev = g("vocab_size"), g("beyond_core_pct"), g("mtld"), g("evidence_n")
    if ctest is not None and wpm is not None and ctest >= 65 and wpm < 118:
        found.append(("AUTOMATIZE", f"C-test {ctest:.0f}% (knowledge present) but {wpm:.0f} wpm (< 118): knowledge–access gap"))
    elif dict_p is not None and wpm is not None and dict_p >= 85 and wpm < 110:
        found.append(("AUTOMATIZE", f"decodes {dict_p:.0f}% but speaks {wpm:.0f} wpm: receptive–productive split"))
    if vocab is not None and beyond is not None and vocab >= 5000 and beyond < 15:
        found.append(("RANGE", f"vocab ~{vocab:.0f} families but only {beyond:.0f}% beyond-core in speech: passive vocabulary"))
    elif wpm is not None and mtld is not None and wpm >= 118 and mtld < 45:
        found.append(("RANGE", f"{wpm:.0f} wpm but MTLD {mtld:.0f}: fluent-but-thin"))
    if ev is not None and ev < 6:
        found.append(("USE", f"evidence {ev:.0f}/14: English not under real load"))
    order = {p: i for i, p in enumerate(PRIORITY)}
    found.sort(key=lambda x: order[x[0]])
    return found

def flags(row):
    """Signals that need a human check before they can become a dial position."""
    out = []
    d = row.get("dict_pct")
    if d is not None and d < 85:
        out.append(f"dictation {d:.0f}% < 85 — decode may be the ceiling, but dict_pct is an inflated upper bound: "
                   f"run the authentic-audio check (novel material) before overriding the dial to DECODE in the reason column")
    return out

def parse_date(x):
    import datetime as _dt
    try: return _dt.date.fromisoformat(str(x)[:10])
    except ValueError: return None

def cycle_rows(rows):
    """Rows that count as cycle closes: each ≥ CYCLE_MIN_DAYS after the previous kept row.
    Returns (kept, latest_is_measurement, gap_days_of_latest)."""
    kept, last = [], None
    for r in rows:
        d = parse_date(r.get("date"))
        if last is None or d is None or (d - last).days >= CYCLE_MIN_DAYS:
            kept.append(r)
            if d is not None: last = d
    if rows and kept and rows[-1] is not kept[-1]:
        d, l = parse_date(rows[-1].get("date")), parse_date(kept[-1].get("date"))
        return kept, True, (d - l).days if d and l else None
    return kept, False, None

def current_dial():
    if not DIAL_LOG.exists():
        return "DEFAULT", 0
    last, n = "DEFAULT", 0
    with open(DIAL_LOG, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip() or line.startswith("date"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3:
                last, n = parts[2], n + 1
    return last, n

def recommend(rows, dial="DEFAULT"):
    if not rows:
        return {"state": "PRE-SEASON", "dial": "DEFAULT",
                "reason": "No baseline row in tracking.tsv. Nothing is adjustable until the diagnostic is run once."}
    latest = rows[-1]
    kept, measurement, gap = cycle_rows(rows)
    profs = profiles(latest)
    fl = flags(latest)
    def out(d):
        if fl: d["flags"] = fl
        return d
    if measurement:
        return out({"state": "MEASUREMENT", "dial": dial, "cycle": len(kept),
                    "reason": f"This row is {gap} days after the previous time trial (< {CYCLE_MIN_DAYS}): a measurement (the week-12 race row), "
                              f"not a cycle close. No lever changes here; score it against the season targets."})
    n = len(kept)
    if n == 1:
        if profs:
            p, why = profs[0]
            return out({"state": "BASELINE", "dial": p, "cycle": 1,
                    "reason": f"Baseline profile → {p}: {why}. "
                              + ("Also applicable, lower priority: " + "; ".join(f"{a} ({b})" for a, b in profs[1:]) if len(profs) > 1 else "")})
        return out({"state": "BASELINE", "dial": "DEFAULT", "cycle": 1,
                "reason": "No dominant weakness at baseline — run the template as written (DEFAULT)."})
    prev = kept[-2]
    metric = TARGET_METRIC.get(dial, "wpm")
    cycle = n  # row n closes cycle n-1
    if metric is None:   # DECODE: held by override, judged by the authentic-audio check, not by this script
        dp, dl = prev.get("dict_pct"), latest.get("dict_pct")
        hint = f" dict_pct moved {dl - dp:+.0f} (upper bound, informative only)." if dp is not None and dl is not None else ""
        return out({"state": "MANUAL", "dial": dial, "cycle": cycle, "metric": None, "delta": None,
                    "reason": f"{dial} has no mechanical target metric: judge it on the monthly authentic-audio check (< 85% = still decode-limited) "
                              f"and write the decision in the reason column.{hint} Other profiles now applicable: "
                              + ("; ".join(f"{a} ({b})" for a, b in profs) if profs else "none") + "."})
    a, b = prev.get(metric), latest.get(metric)
    if a is None or b is None:
        # absent data is not a failed threshold: never spend a lever on a blank
        return out({"state": "INCOMPLETE", "dial": dial, "cycle": cycle, "metric": metric, "delta": None,
                "reason": f"{dial}'s target metric {metric} is missing in the {'previous' if a is None else 'latest'} tracking row. "
                          f"Hold the dial; complete the module (or the export) before any adjustment."})
    delta = b - a
    thr = NOISE.get(metric, 0)
    moved = delta >= thr if thr else delta > 0
    if n == 2:
        # first time trial: cycle-1 deltas belong to the plan as a whole (docs/TARGET.md);
        # the dial moves only on an unambiguous profile — exactly one applies and it is not the current one
        if len(profs) == 1 and profs[0][0] != dial:
            p, why = profs[0]
            return out({"state": "TIME-TRIAL", "dial": p, "cycle": cycle, "metric": metric, "delta": delta,
                    "reason": f"First time trial: cycle-1 delta ({metric} {delta:+.0f}) is credited to the plan as a whole, "
                              f"but the profile is unambiguous → {p}: {why}. One lever changes."})
        why_hold = ("no profile applies" if not profs else
                    f"{len(profs)} profiles apply ({', '.join(a for a, _ in profs)}) — ambiguous" if len(profs) > 1 else
                    f"the only profile is the current dial")
        return out({"state": "TIME-TRIAL", "dial": dial, "cycle": cycle, "metric": metric, "delta": delta,
                "reason": f"First time trial: {metric} {delta:+.0f} (threshold {thr}) is credited to the plan as a whole; {why_hold}. "
                          f"Hold {dial}; the threshold rule applies from cycle 2."})
    if moved:
        return out({"state": "TIME-TRIAL", "dial": dial, "cycle": cycle, "metric": metric, "delta": delta,
                "reason": f"{dial} held: its target metric {metric} moved {delta:+.0f} (≥ threshold {NOISE.get(metric, 0)}). Keep the lever where it is."})
    # Not moved: move to next-priority profile that is not the current one
    for p, why in profs:
        if p != dial:
            return out({"state": "TIME-TRIAL", "dial": p, "cycle": cycle, "metric": metric, "delta": delta,
                    "reason": f"{dial}'s target {metric} moved {delta if delta is not None else 'n/a'} (< threshold {NOISE.get(metric, 0)}). "
                              f"Next-priority profile → {p}: {why}. One lever changes."})
    if profs and profs[0][0] == dial:
        return out({"state": "TIME-TRIAL", "dial": dial, "cycle": cycle, "metric": metric, "delta": delta,
                "reason": f"{dial}'s target {metric} did not move ({delta if delta is not None else 'n/a'}), and no other profile applies. "
                          f"Hold one more cycle; if flat again, abandon {dial} (twice-failed rule) and check weekly load first — a plateau on an unrun plan is not a plateau."})
    return out({"state": "TIME-TRIAL", "dial": "DEFAULT", "cycle": cycle, "metric": metric, "delta": delta,
            "reason": f"{metric} did not move and no profile applies → DEFAULT. Check logs/weekly.tsv adherence before reading this as a plateau."})

def selftest():
    import datetime as _dt
    def row(**k):
        base = {"date": "2026-01-01", "ctest_pct": 70, "vocab_size": 5000, "dict_pct": 90,
                "ei_pct": 60, "wpm": 125, "mtld": 60, "beyond_core_pct": 20, "evidence_n": 9}
        base.update(k); return base
    def season(*specs, gaps=None):
        """rows spaced 35 days apart (weeks 0/5/10) unless gaps (days) are given."""
        d, out, gaps = _dt.date(2026, 1, 1), [], gaps or [35] * len(specs)
        for i, sp in enumerate(specs):
            out.append(row(date=d.isoformat(), **sp)); d += _dt.timedelta(days=gaps[i])
        return out
    assert recommend([])["state"] == "PRE-SEASON"
    assert recommend([row()])["dial"] == "DEFAULT"
    r = recommend([row(dict_pct=70)])
    assert r["dial"] == "DEFAULT" and r["flags"] and "DECODE" in r["flags"][0], "low dictation is a flag, never a mechanical DECODE: %r" % r
    assert recommend([row(wpm=100)])["dial"] == "AUTOMATIZE"
    r = recommend([row(dict_pct=70, wpm=100)])
    assert r["dial"] == "AUTOMATIZE" and r["flags"], r
    assert recommend([row(beyond_core_pct=10)])["dial"] == "RANGE"
    assert recommend([row(evidence_n=3)])["dial"] == "USE"
    # first time trial (n == 2): deltas belong to the plan; move only on an unambiguous profile
    r = recommend(season({"wpm": 100}, {"wpm": 104}), dial="AUTOMATIZE")
    assert r["dial"] == "AUTOMATIZE" and "First time trial" in r["reason"], r          # only profile == current dial → hold
    r = recommend(season({"wpm": 100}, {"wpm": 104, "evidence_n": 3}), dial="AUTOMATIZE")
    assert r["dial"] == "AUTOMATIZE" and "ambiguous" in r["reason"], r                 # two profiles → hold
    r = recommend(season({}, {"evidence_n": 3}), dial="DEFAULT")
    assert r["dial"] == "USE" and "unambiguous" in r["reason"], r                      # one profile, not current → move
    # cycle 2+: held when target moved
    r = recommend(season({"wpm": 95}, {"wpm": 100}, {"wpm": 113}), dial="AUTOMATIZE")
    assert r["dial"] == "AUTOMATIZE" and "held" in r["reason"], r
    # cycle 2+: not moved -> next profile
    r = recommend(season({"wpm": 95}, {"wpm": 100}, {"wpm": 104, "evidence_n": 3}), dial="AUTOMATIZE")
    assert r["dial"] == "USE", r
    # cycle 2+: not moved, no other profile -> hold with warning
    r = recommend(season({"wpm": 95}, {"wpm": 100}, {"wpm": 104}), dial="AUTOMATIZE")
    assert r["dial"] == "AUTOMATIZE" and "twice-failed" in r["reason"], r
    # USE is judged on evidence_n with its own threshold (+3), not on +1
    r = recommend(season({"evidence_n": 2}, {"evidence_n": 3}, {"evidence_n": 4}), dial="USE")
    assert r["dial"] != "USE" or "held" not in r["reason"], r
    r = recommend(season({"evidence_n": 2}, {"evidence_n": 3}, {"evidence_n": 6}), dial="USE")
    assert r["dial"] == "USE" and "held" in r["reason"], r
    # a blank target metric is INCOMPLETE, never a lever change
    r = recommend(season({"wpm": 95}, {"wpm": 100}, {"wpm": None, "evidence_n": 3}), dial="AUTOMATIZE")
    assert r["state"] == "INCOMPLETE" and r["dial"] == "AUTOMATIZE", r
    # DECODE set by override: judged by the authentic-audio check, never moved by this script
    r = recommend(season({"dict_pct": 70}, {"dict_pct": 74}, {"dict_pct": 76, "evidence_n": 3}), dial="DECODE")
    assert r["state"] == "MANUAL" and r["dial"] == "DECODE" and "USE" in r["reason"] and r["flags"], r
    # week-12 race row: 14 days after time trial 2 → a measurement, no lever
    rows = season({"wpm": 95}, {"wpm": 100}, {"wpm": 104, "evidence_n": 3}, {"wpm": 106, "evidence_n": 3}, gaps=[35, 35, 14, 0])
    r = recommend(rows, dial="AUTOMATIZE")
    assert r["state"] == "MEASUREMENT" and r["dial"] == "AUTOMATIZE" and r["cycle"] == 3, r
    assert cycle_rows(rows)[0][-1] is rows[2]
    print("dial.py selftest: OK")

def main():
    if "--selftest" in sys.argv:
        return selftest()
    rows = read_rows()
    dial, _ = current_dial()
    rec = recommend(rows, dial)
    if "--json" in sys.argv:
        print(json.dumps(rec, indent=1)); return
    print(f"[{rec['state']}] dial → {rec['dial']}")
    print(rec["reason"])
    for f in rec.get("flags") or []: print("flag:", f)

if __name__ == "__main__":
    main()
