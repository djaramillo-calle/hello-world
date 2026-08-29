# English Signal Check — instrument specification

A self-administered diagnostic battery for adult L2 English, built to give a
**domain-resolved** profile rather than a single score, and to be re-run
frequently enough to detect real change.

## Why not just take a free exam

| Test | Free | Skills | Verdict |
|---|---|---|---|
| **EF SET** | yes | reading, listening | The only free, standardised, CEFR-calibrated test with published correlation studies against TOEFL iBT. **Use it as the external anchor.** Tests nothing productive. |
| **Duolingo English Test** | no (~$65) | four skills, adaptive | Strong validity evidence and predictive validity against GPA. Not free, and not re-runnable monthly. |
| **DIALANG** | was | reading, writing, listening, grammar, vocab | Genuinely diagnostic and CEFR-based, but Lancaster's pro-bono hosting ended in 2024. Do not build on it. |
| **Cambridge / Oxford free placement tests** | yes | reading, grammar | Indicative only; short, no published validity, ceiling out fast. |
| **LexTALE** | yes | vocabulary | 5 minutes, validated — but a 2022 partial replication found only low-to-moderate correlation with global proficiency, and it ceilings for advanced learners. |

None of them measures speaking, which is the binding constraint for
conversational use. Hence this battery.

## The six modules

### 1. C-test — general proficiency
Four passages of ascending difficulty. First sentence intact; thereafter the
second half of every second word is deleted (`Math.ceil(len/2)` retained),
20 gaps per passage, 80 total. Exact-match scoring.

**Why:** C-tests report Cronbach's α ≈ .87–.92, parallel-forms r ≈ .82,
test–retest r ≈ .76, and load on a general language factor alongside listening
and speaking measures. Highest reliability per minute of any format, which is
what makes it the right instrument for frequent tracking.

**Read the ceiling, not the total.** The hardest passage held at ≥60% localises
where automatic processing fails.

### 2. Yes/No vocabulary test — breadth
64 real words (8 per 1k band, 1k–8k) + 32 pseudowords, deterministically
shuffled so item order is identical every run.

Corrected score per band: `max(0, (h − f) / (1 − f))`, summed × 1000.

**Validity gate:** the correction cannot recover an estimate once the
false-alarm rate is high — a test-taker marking "know" on 90% of non-words
still scores at ceiling. Above **f > 0.30 the run is reported as void**, not
merely low-confidence.

**Caveat:** band assignments are frequency estimates, not a BNC extract. They
are *stable* across administrations, which is what tracking requires;
they are *approximate* in absolute terms.

### 3. Partial dictation — listening decode
Ten sentences, rate ramping 0.95× → 1.40×, two plays each, scored by
order-insensitive token overlap. Reports a **speed ceiling**: the fastest rate
still decoded at ≥80%.

**Why:** Oller found dictation the single strongest predictor of overall
proficiency; later work confirms it taps both bottom-up and top-down listening.

**Caveat:** browser speech synthesis is cleaner than real speech — no
reduction, no overlap, no accent variety. Treat the score as an **upper bound**
and run the authentic-audio protocol monthly (below).

### 4. Elicited imitation — oral encoding
Eight sentences of ascending length. Hear → judge whether it makes sense →
repeat aloud. Self-rated 0–4.

**Why:** sentences beyond verbatim memory span can only be reproduced by
reconstruction from grammar, which is why EIT correlates with OPI ratings
rather than with memory span. The sense-judgement blocks acoustic parroting.

**Caveat:** self-rating makes this the softest number in the battery. It is
still useful for tracking, because the rater's generosity is roughly constant
across sessions.

### 5. Speaking sample — output
Unprepared 2-minute monologue on a drawn prompt (tagged: work, opinion,
narrative, social, transactional, abstract), transcribed **verbatim**, then
analysed for:

- **Speech rate (wpm)** — the most reliable single correlate of oral
  proficiency. Corpus reference points: B2 ≈ 118 wpm, C1 ≈ 142 wpm.
- **Filler ratio** and **self-repair rate** — planning pressure.
- **MTLD** (both directions, TTR threshold 0.72) — lexical diversity.
- **Beyond-core ratio** — share of tokens outside an embedded ~1,500-word
  high-frequency list. The list is an approximation, not a corpus extract;
  it is identical on every run, so the measure is stable even where the list
  is imperfect.

### 6. Evidence inventory — real-world use
Fourteen **behavioural** items ("did you, in the last 14 days"), not
confidence ratings — CEFR self-assessment correlates inconsistently with test
scores, so asking what happened beats asking how you feel.

## Interpretation rules

The report cross-reads domains and names the common failure profiles:
knowledge–access gap, fluent-but-thin, receptive–productive split, passive
vocabulary, use-constrained. These are the readings that change what you
should actually do.

## Calibration honesty

Bands are anchored to typical published values, **not** to a normed sample.
Treat any absolute level as ± one CEFR sub-level.

What the battery *is* reliable for is **change**: identical items, identical
scoring, so movement above the per-instrument noise threshold is signal.
Thresholds used in the delta table:

| Measure | Noise threshold |
|---|---|
| C-test | ±8 points |
| Vocabulary | ±500 families |
| Dictation | ±10 points |
| Speech rate | ±12 wpm |
| MTLD | ±8 |

**Item memory is the main threat to repeat validity.** By the third run you
will half-remember C-test answers. Treat repeat scores as a floor.

## Monthly authentic-audio check

1. Podcast or interview with a published transcript, topic you have no
   expertise in.
2. 60 seconds never heard before. Transcribe. Two listens maximum.
3. Score = words correct ÷ words in reference transcript.
4. Below 85% is where real conversation starts failing. The gap between this
   and the synthetic dictation score is your real-speech penalty.

## Quarterly external anchor

Take the free EF SET (~50 min). Record the CEFR level beside your C-test
percentage. Over three or four rounds this yields a personal conversion
between this battery and an external scale — the one thing a home-built
instrument cannot supply for itself.

## Running the tests

```
python3 scripts/extract-scripts.py && node scripts/run-tests.js
```

Checks gap counts, item-bank integrity, the validity gate, MTLD behaviour and
dictation scoring. See `logs/` for recorded runs.
