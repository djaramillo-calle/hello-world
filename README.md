# Adult English: diagnosis and improvement

Working repo for an evidence-based English improvement programme — the
research behind the method, and a self-administered instrument to measure
where you actually are and whether you are moving.

## Contents

| Path | What it is |
|---|---|
| `diagnostic.html` | **English Signal Check** — the diagnostic battery. Open it in a browser; nothing is transmitted, results stay in local storage. |
| `routine.html` | **English Runbook** — the daily routine card: weekly template, minimum-viable day, channel briefs, focus dial. |
| `observations.md` | Chat-harvested English observation log: patterns → SRS cards and tutor briefs; never a scored metric. |
| `seed-deck.csv` | Seed SRS deck — 33 production-format cards for the Anki "English Runbook" deck. |
| `docs/plan/` | The three candidate routine plans (interaction-first, input-engine, periodized) and the adjudicated final merge. |
| `docs/METHOD.md` | Instrument specification: what each module measures, how it is scored, validity evidence, calibration caveats. |
| `docs/adult-language-learning.html` | Evidence review of adult L2 methods, aimed at conversational ability. |
| `docs/SOURCES.md` | Reference list for both. |
| `docs/kindle-integration.md` | Kindle Vocabulary Builder research + the vocab.db → repo bridge workflow. |
| `tracking.tsv` | Progress log. One row per session. |
| `scripts/` | Assertion-based test suite driving the shipped page in jsdom, plus the Kindle vocab.db merge script. |
| `logs/` | Recorded verification runs; local sessions also drop Anki/Kindle bridge stats here. |
| `docs/audit/` | Double-blind audit: two independent reports and the binding reconciliation verdict. |

## Using it

1. **Baseline.** Open `diagnostic.html`, run all six modules in one sitting
   (~60 min). Hit *Save this session to history*, then *Copy result row* and
   append the line to `tracking.tsv`.
2. **Re-run every 5 weeks** — the adjudicated cadence (`docs/plan/final-plan.md`). More often measures noise plus item memory.
3. **Monthly:** the authentic-audio dictation check (see `docs/METHOD.md`) —
   the synthetic voice in module 3 flatters you.
4. **Quarterly:** take the free [EF SET](https://www.efset.org/) as an
   external CEFR anchor and record the level next to your C-test score.

## What this instrument is and isn't

It is **not calibrated against a normed sample**. Absolute bands are good to
about ± one CEFR sub-level. It is built to be reliable for **change** —
identical items and scoring every run — so movement above the per-measure
noise thresholds in `docs/METHOD.md` is real signal.

## Development

```bash
npm install          # once — jsdom for the DOM-driven suite
node scripts/test.js # asserts scoring, guards, and item-bank invariants; non-zero exit on failure
```

`node_modules/` is gitignored.
