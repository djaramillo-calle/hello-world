#!/usr/bin/env python3
"""Mechanical focus-dial recommendation from tracking.tsv.

    python3 scripts/dial.py            # human-readable recommendation
    python3 scripts/dial.py --json     # machine-readable
    python3 scripts/dial.py --selftest # exercise the rules on synthetic data

Implements docs/TARGET.md "Adjustment protocol" and the profile -> dial
mapping in docs/plan/final-plan.md. It never edits anything; the Friday
review logs its output to logs/dial-log.tsv and a human may override —
in writing, next to the recommendation.
"""
import csv, json, pathlib, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TRACKING = REPO / "tracking.tsv"
DIAL_LOG = REPO / "logs" / "dial-log.tsv"

# Noise thresholds (docs/METHOD.md) — movement at or above = signal
NOISE = {"ctest_pct": 8, "vocab_size": 1100, "dict_pct": 10, "wpm": 12, "mtld": 8}
# Which metric each dial position is accountable for
TARGET_METRIC = {"DEFAULT": "wpm", "DECODE": "dict_pct", "AUTOMATIZE": "wpm",
                 "RANGE": "mtld", "USE": "evidence_n"}
PRIORITY = ["DECODE", "AUTOMATIZE", "RANGE", "USE"]

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
    if dict_p is not None and dict_p < 85:
        found.append(("DECODE", f"dictation {dict_p:.0f}% is below the 85% decode band"))
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
    n = len(rows)
    profs = profiles(latest)
    if n == 1:
        if profs:
            p, why = profs[0]
            return {"state": "BASELINE", "dial": p, "cycle": 1,
                    "reason": f"Baseline profile → {p}: {why}. "
                              + ("Also applicable, lower priority: " + "; ".join(f"{a} ({b})" for a, b in profs[1:]) if len(profs) > 1 else "")}
        return {"state": "BASELINE", "dial": "DEFAULT", "cycle": 1,
                "reason": "No dominant weakness at baseline — run the template as written (DEFAULT)."}
    prev = rows[-2]
    metric = TARGET_METRIC.get(dial, "wpm")
    a, b = prev.get(metric), latest.get(metric)
    if a is None or b is None:
        moved, delta = None, None
    else:
        delta = b - a
        thr = NOISE.get(metric, 0)
        moved = delta >= thr if thr else delta > 0
    cycle = n  # row n closes cycle n-1
    if moved:
        return {"state": "TIME-TRIAL", "dial": dial, "cycle": cycle, "metric": metric, "delta": delta,
                "reason": f"{dial} held: its target metric {metric} moved {delta:+.0f} (≥ threshold {NOISE.get(metric, 0)}). Keep the lever where it is."}
    # Not moved: move to next-priority profile that is not the current one
    for p, why in profs:
        if p != dial:
            return {"state": "TIME-TRIAL", "dial": p, "cycle": cycle, "metric": metric, "delta": delta,
                    "reason": f"{dial}'s target {metric} moved {delta if delta is not None else 'n/a'} (< threshold {NOISE.get(metric, 0)}). "
                              f"Next-priority profile → {p}: {why}. One lever changes."}
    if profs and profs[0][0] == dial:
        return {"state": "TIME-TRIAL", "dial": dial, "cycle": cycle, "metric": metric, "delta": delta,
                "reason": f"{dial}'s target {metric} did not move ({delta if delta is not None else 'n/a'}), and no other profile applies. "
                          f"Hold one more cycle; if flat again, abandon {dial} (twice-failed rule) and check weekly load first — a plateau on an unrun plan is not a plateau."}
    return {"state": "TIME-TRIAL", "dial": "DEFAULT", "cycle": cycle, "metric": metric, "delta": delta,
            "reason": f"{metric} did not move and no profile applies → DEFAULT. Check logs/weekly.tsv adherence before reading this as a plateau."}

def selftest():
    def row(**k):
        base = {"date": "2026-01-01", "ctest_pct": 70, "vocab_size": 5000, "dict_pct": 90,
                "ei_pct": 60, "wpm": 125, "mtld": 60, "beyond_core_pct": 20, "evidence_n": 9}
        base.update(k); return base
    assert recommend([])["state"] == "PRE-SEASON"
    assert recommend([row()])["dial"] == "DEFAULT"
    assert recommend([row(dict_pct=70)])["dial"] == "DECODE"
    assert recommend([row(wpm=100)])["dial"] == "AUTOMATIZE"
    assert recommend([row(dict_pct=70, wpm=100)])["dial"] == "DECODE", "decode outranks automatize"
    assert recommend([row(beyond_core_pct=10)])["dial"] == "RANGE"
    assert recommend([row(evidence_n=3)])["dial"] == "USE"
    # cycle: held when target moved
    r = recommend([row(wpm=100), row(wpm=113)], dial="AUTOMATIZE")
    assert r["dial"] == "AUTOMATIZE" and "held" in r["reason"], r
    # cycle: not moved -> next profile
    r = recommend([row(wpm=100), row(wpm=104, evidence_n=3)], dial="AUTOMATIZE")
    assert r["dial"] == "USE", r
    # cycle: not moved, no other profile -> hold with warning
    r = recommend([row(wpm=100), row(wpm=104)], dial="AUTOMATIZE")
    assert r["dial"] == "AUTOMATIZE" and "twice-failed" in r["reason"], r
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

if __name__ == "__main__":
    main()
