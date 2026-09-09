# The race — season definition

A training program without a race is maintenance. This file defines the
race, the season that leads to it, and the numbers that count as "made it".
Everything here is machine-readable by `scripts/dial.py` and
`scripts/build-progress.py`; edit the constants there when this file changes.

## Season structure (12 weeks from baseline)

| Week | Phase | What happens |
|---|---|---|
| **0** | Baseline | Run `diagnostic.html` once, rested, ~60 min. Row 1 in `tracking.tsv`. Targets are computed from this row. Dial set. Season clock starts. |
| 1–4 | Cycle 1 — build | Runbook at full load. Weekly log every Friday. |
| 5 | **Time trial 1** | Mon–Wed minimum-viable days (deload); weekend diagnostic → row 2. Dial reviewed (one lever max). |
| 6–9 | Cycle 2 — build | Runbook at the new dial position. |
| 10 | **Time trial 2** | Deload + diagnostic → row 3. Dial reviewed. |
| 11 | Sharpen | Cycle 3 at full load, race booked. |
| **12** | **Race week** | The road race (below) + diagnostic → row 4. Season review. Next season's race defined. |

Weeks are counted from the Monday after the baseline. If the baseline slips,
the whole calendar slips with it — the season never starts without a row 1.

## The race (week 12)

Two events, both required:

1. **The road race — a real conversation under real conditions.** 30 minutes,
   unscripted, with a proficient English speaker you have **never spoken to
   before** (a new tutor booked for the occasion, an exchange partner, a
   stranger at a meetup). Recorded. Afterwards they rate you on the
   9-point comprehensibility scale used in the research literature
   (1 = very easy to understand … 9 = very difficult).
   **Target: ≤ 3** ("easy to understand"). This is the chip time — the
   outcome the whole program exists for, judged by someone with no stake
   in being kind.
2. **Time trial 3 — the diagnostic**, same conditions as every other run,
   scored against the targets below.

## Targets (set at baseline, never moved mid-season)

Each target is **baseline + one noise threshold** — the smallest movement the
instrument can call real signal. Modest by design: 12 weeks is two full
cycles, and the evidence review's own predictions put wpm movement at
"≥ +12 by cycle 3". Hitting a signal-level gain on every domain in one season
is a strong result; hitting it on the domain the dial targeted is the minimum.

| Metric | Target rule | Noise threshold | Absolute floor (whichever is higher) |
|---|---|---|---|
| Speech rate `wpm` | baseline + 12 | ±12 | 120 |
| C-test `ctest_pct` | baseline + 8 | ±8 | 75 |
| Dictation `dict_pct` | baseline + 10 | ±10 | 85 |
| Vocabulary `vocab_size` | baseline + 1,100 | ±1,100 | — (lags by design; RANGE dial only) |
| Evidence `evidence_n` | baseline + 3 | — (behavioural count) | 10 / 14 |
| Filler ratio (speaking sample) | ≤ 5% | — | — |
| MTLD | baseline + 8 | ±8 | — (lags by design) |

The **primary target** is whichever metric the dial is pointed at (DEFAULT
dial → `wpm`). The season is a success if the primary target and the road
race are both met; a partial if one is; a re-plan if neither.

## Weekly load (the training log — `logs/weekly.tsv`)

A runner logs mileage every week; this program logs load every Friday. The
floor that must hold every week, no exceptions:

| Load metric | Floor | Source |
|---|---|---|
| Conversations (≥1 human) | **2** | self-report in the Friday close (AI + tutor) |
| SRS review days | 5 | `logs/anki-stats.json` reviews-per-day |
| Recorded speaking (4/3/2 or practice) | 1 | `logs/practice/` |
| Attended listening days | 5 | self-report |

Two consecutive weeks below the conversation floor triggers the runbook's
automatic downgrade rule (Thursday → 20′ AI, non-negotiable). Load is
**adherence**, not ability: it never feeds `tracking.tsv`, and it is the
first thing checked when a time trial disappoints — you cannot diagnose a
plateau without knowing whether the plan was actually run.

## Adjustment protocol (mechanical)

`scripts/dial.py` reads `tracking.tsv`, applies the profile → dial mapping
from `docs/plan/final-plan.md` and the noise thresholds above, and prints the
recommendation with its reasons. It is run at every time-trial week-close and
its output is logged to `logs/dial-log.tsv`. Humans (and Claude) may
disagree with it — but the disagreement gets written down next to the
recommendation, so the record shows every override.

Rules the script enforces:
- No baseline → `PRE-SEASON`; nothing is adjustable.
- Cycle 1 deltas belong to the plan as a whole; the dial can move at the
  first time trial only if the profile is unambiguous.
- From cycle 2: keep the dial if its target metric moved ≥ threshold;
  otherwise move to the next-priority profile (decode → automatize → range
  → use). One lever per cycle. A position that fails twice is abandoned.
- Repeat scores are floors (item memory): upward moves are trusted, flat
  ones are ambiguous — the monthly authentic-audio check breaks ties on
  decode.
