# Adult English: diagnosis and improvement

Working repo for an evidence-based English improvement programme — the
research behind the method, and a self-administered instrument to measure
where you actually are and whether you are moving.

## Contents

| Path | What it is |
|---|---|
| `diagnostic.html` | **English Signal Check** — the diagnostic battery. Open it in a browser; nothing is transmitted, results stay in local storage. |
| `docs/METHOD.md` | Instrument specification: what each module measures, how it is scored, validity evidence, calibration caveats. |
| `docs/adult-language-learning.html` | Evidence review of adult L2 methods, aimed at conversational ability. |
| `docs/SOURCES.md` | Reference list for both. |
| `tracking.tsv` | Progress log. One row per session. |
| `scripts/` | Test tooling for the instrument's scoring code. |
| `logs/` | Recorded verification runs. |

## Using it

1. **Baseline.** Open `diagnostic.html`, run all six modules in one sitting
   (~60 min). Hit *Save this session to history*, then *Copy result row* and
   append the line to `tracking.tsv`.
2. **Re-run every 4–6 weeks.** More often measures noise plus item memory.
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
python3 scripts/extract-scripts.py   # pull JS out of the HTML
node scripts/run-tests.js            # check gap counts, scoring, validity gate
```

`scripts/.build/` is generated and gitignored.
