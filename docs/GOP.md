# Local pronunciation scoring (GOP) — the parallel-run protocol

**Status: validation, not adoption.** Written 2026-09-19, BEFORE any result was
seen. The criteria below are pre-registered on purpose: after a month of data it
is too easy to decide that whatever came out was what we wanted.

## Why

Azure's F0 tier gave out after eight days (the accounting is in CLAUDE.md), and
S0 costs ~$1.30 per audio hour with no free allowance. Hosted alternatives are
worse: SpeechAce and SpeechSuper bill ~$1.92/audio hour and cap a request at
30s–2min, which is the wrong shape for a 15–84 minute read. Google and AWS do
not offer phoneme-level assessment at all.

A local scorer costs nothing per run and **cannot run out**, which matters more
than the money: the quota is what stopped the daily loop, not the price.

## What GOP does and does not replace

Goodness of Pronunciation gives **per-phoneme** scores from a phoneme-recognition
model — for each phoneme the reference text says should be there, how well the
audio supports it. That is exactly the input the confusion classes are built
from, so it can replace:

- Azure `accuracy` (utterance-level, aggregated from phonemes)
- Azure per-phoneme identities and scores → `th`, `b/v`, `i/ii`, `j/y`, `s/z`,
  `-ed`, `schwa`, `s-cluster`, `h`, `cat/cut` (`PH2CLASS` already exists in
  `scripts/practice-review.py` and is reused unchanged)
- Azure `completeness` (coverage of the reference by the alignment)

It does **not** produce `fluency` or `prosody`. Those are separate measurements
and we already compute their ingredients locally — pause structure and
articulation rate (de Jong & Wempe) and pitch (parselmouth) are in
`practice-ingest.py` today and cost nothing. Whether a defensible fluency number
can be built from them is a SEPARATE question and not part of this protocol.

## The two validation sets

**1. speechocean762 — the primary set, because it has HUMAN scores.**
5,000 utterances from 250 non-native speakers, with per-phoneme accuracy labels
(0–2) and utterance-level accuracy/fluency/prosody/completeness/total (0–10)
from human raters. This lets both engines be measured against people instead of
against each other.

> **Azure is not ground truth.** It is the incumbent. "GOP agrees with Azure" is
> a statement about agreement, not about correctness — and we already know Azure
> can be wrong here, because en-GB returned a prosody number for a locale that
> does not support prosody, and we read those fifties as a finding about his
> delivery for two days.

**2. His six reads — the secondary set, for HIS voice and HIS material.**
2026-09-10 to 09-16, 197 minutes, already carrying Azure scores at no further
cost. n=6 with accuracy spanning 88.4–96.1 is far too small and too narrow to
validate a *series*; it is used only to check that the **confusion classes**
come out the same on real audio of his.

## Pre-registered criteria

**Primary — phoneme agreement with humans (speechocean762, ~300 held-out
utterances, both engines on the SAME utterances):**

- GOP's correlation with human per-phoneme accuracy must be **≥ Azure's minus
  0.05**. Not better than Azure — as good as, within a small margin. Azure's own
  number on this set is measured here, not assumed.
- Mispronunciation detection F1 at a matched operating point: same rule.
- Utterance-level accuracy: Pearson with the human total, same rule.

Azure on ~300 short utterances is roughly 25 minutes of audio — about $0.55 on
S0, or free inside a fresh month's F0 allowance.

**Secondary — confusion classes on his six reads:**

- The **top three classes by count must match Azure's top three as a set**
  (currently i/ii 50, s/z 44, schwa 32). Order may differ.
- Spearman across all ten classes **≥ 0.7**.

**Operational:**

- A 30-minute read scores in under 30 minutes on one CPU core, and is
  deterministic (same audio in, same numbers out).
- Runs from a clean container with no key, no account and no network.

**Stop rule.** If the primary criterion fails, we do not switch and we do not
keep tinkering: budget is two weekends. A negative result is a real result and
gets written into this file with its numbers.

## The parallel month

Azure is out of quota until October, so the retrospective work (both validation
sets) happens first and costs nothing. From the day S0 is enabled:

- every read is scored by BOTH engines;
- GOP output lands in the record under its own `gop` key and in a `gop` column
  family in the ledger — **it never overwrites an Azure field**;
- the ledger's `reads` rows stay Azure-sourced for the whole month;
- **nothing from GOP reaches `tracking.tsv`**, during the trial or after it. The
  same rule that governs every other sensor.

## If we do switch

It is an instrument change and gets treated like the locale change that taught
us this: every read row already carries `locale`; it gains `engine`. Azure rows
and GOP rows are **different series** and never share a line. The switch is
dated in CLAUDE.md and in the ledger's notes, and the reason is recorded with
the numbers that justified it.
