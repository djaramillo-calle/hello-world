# Season audit — 2026-09-09

**Goal under audit:** the repo must be actionable and result in a daily
learning routine — treated as a sport (a sub-20 5K): measurable, adaptable,
tailored to strengths and weaknesses, with an effective feedback loop.

## State at audit (10 days after setup)

| Component | State |
|---|---|
| Diagnostic (form v2, audited) | built, published, 72/72 tests green — **never run** |
| Runbook (adjudicated plan) | built, published — no clock times tied to the real calendar |
| SRS deck | 33 seed cards imported 2026-08-30 — **0 reviews** in the last stats export |
| Practice recording pipeline | built by local sessions — **0 recordings** ingested |
| Kindle bridge | built — never synced |
| Observation log + Friday review | running (digest 1 written 2026-09-04) |
| `tracking.tsv` | **header only — no baseline** |

Verdict: a complete training environment with no training in it. Every
adaptive mechanism was gated on a baseline that had not happened, and
nothing in the system made that state loud.

## Findings against the sport frame

| # | Finding | Severity | Remediation |
|---|---|---|---|
| F1 | **No race.** No target number, no date. | Critical | `docs/TARGET.md`: 12-week season from baseline; time trials at weeks 5/10/12; the road race (30-min conversation with a stranger, comprehensibility ≤3/9) plus targets = baseline + one noise threshold per domain, with absolute floors |
| F2 | **Season not started** — baseline not run. | Blocking (user) | Board and runbook now state PRE-SEASON explicitly with the one action that starts the clock; nothing else can substitute |
| F3 | **No training log** — only the 5-week time trial measured anything; weekly load was invisible. | Major | `scripts/weekly-rollup.py` → `logs/weekly.tsv`: SRS days/reviews (from Anki stats), recordings + wpm/filler means (from practice logs), dial, floor check; self-report columns for conversations/listening |
| F4 | **Adaptation was prose.** Dial rules lived in a document; nothing computed them. | Major | `scripts/dial.py`: mechanical profile → dial mapping with noise thresholds, held/moved/abandoned logic, `logs/dial-log.tsv` for overrides in writing; self-tested |
| F5 | **No pace chart.** No trajectory-vs-target view. | Major | `scripts/build-progress.py` → `progress.html` (Season Board): hero season clock, load tiles with floors, per-domain time-trial panels with target rule and noise band, weekly-load heat grid, profile table; validated palette, light/dark, tooltips + table views; rendered and inspected in Chromium |
| F6 | Runbook had no clock times. | Minor | Slots from the real calendar written into the runbook (06:45 / 13:00 / 17:20 / Fri 18:15 / 20:45 / Sat 09:30 trial weeks) |
| F7 | Feedback loop computed nothing mechanical; stats stale. | Major | Friday Routine rewritten: pull → digest → rollup → dial → rebuild board → republish → push, and asks for the two self-report numbers |
| F8 | Calendar events never created (user-gated, unconfirmed). | Flag | Still awaiting confirmation — not created |
| F9 | No single verification entry point across JS + Python tooling. | Minor | `scripts/check.sh` (jsdom suite + all Python self-tests + syntax checks) |

## What the fixes do NOT do

- They do not run the baseline. That is the athlete's first time trial and
  only the athlete can run it. Until then: PRE-SEASON on every surface.
- They do not create calendar events (gated by the user).
- They do not turn adherence into a proficiency score: `logs/weekly.tsv`
  is load, and the board says so on every view.

## Verification

- `bash scripts/check.sh` → all green (72 jsdom assertions; three Python
  self-tests incl. a two-trial in-season fixture).
- Season Board rendered in headless Chromium for the real pre-season state
  and a synthetic week-6 fixture, light and dark; zero page errors; all
  six panels, the load grid and the profile table present. Two visual
  defects found and fixed on inspection (time-trial index concatenation;
  meaningless pre-season axis ticks).
- Chart palette validated with the dataviz validator against the repo's
  own light (`#FBFBF9`) and dark (`#1B201D`) surfaces: all checks pass.
