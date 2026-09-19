# PERIODIZED DELIBERATE PRACTICE — Daily English Routine

**For:** one adult intermediate learner; conversation-first; 45–60 min weekdays across three anchors (morning / lunch / evening); no baseline yet.
tracking.tsv schema: `date, ctest_pct, vocab_size, dict_pct, ei_pct, wpm, mtld, beyond_core_pct, evidence_n`.

## 1. Philosophy in three sentences

Skill-acquisition theory says conversational ability is built in stages — declarative knowledge → proceduralization → automatization — and each stage responds to a *different* kind of practice, so training should come in blocks that target the current bottleneck rather than a static weekly mix. The diagnostic battery already re-runs every 4–6 weeks and reports *which domain* is failing (METHOD.md interpretation rules), which gives us exactly the sensor a periodized program needs: each block is chosen by the last profile and falsified or confirmed by the next one. The drills themselves are individually the best-evidenced items in the literature — HVPT (g = 0.92 perception, 0.77 production), 4/3/2 (Thai & Boers: the shrinking time limit, not mere repetition, is the active ingredient), task repetition (2025 meta: accuracy and complexity gains), chunk instruction, spacing/retrieval (Kim & Webb) — and the review's own protocol endorses "block, then interleave."

**Strongest evidence for:** the review's Phase 3 verdict — "this is the phase most self-directed learners never enter, and it is where conversational ability is actually made" — plus the effect-size table: the drills this plan schedules are precisely the interventions with the largest, most durable, most replicated effects. And the "block, then interleave" finding (Suzuki et al.; Hwang) is direct evidence that *sequenced concentration* beats a constant mix for structures not yet fluent.

**Strongest evidence against — stated honestly:** (a) implicit exposure beats explicit/deliberate work on *delayed* tests (g = 1.76 vs 0.77, Kang et al.), so a drill-heavy plan risks fast gains that decay while under-supplying the input volume that sticks; this plan therefore protects a daily input floor inside every block. (b) The mesocycle concept itself is imported from motor learning and sport — there is no L2 meta-analysis of "4-week blocks vs static template"; the closest support is block-then-interleave, which is a within-session finding. (c) The review is blunt that "the variance between committed learners is dominated by hours and interaction quality, not method," and deliberate-practice plans have the highest complexity and adherence cost of any design; if periodization costs even one adherent hour a week, it has negative expected value.

## 2. Mesocycle design

Each mesocycle = **5 weeks**, inside the diagnostic's 4–6-week cadence:

| Week | Content |
|---|---|
| 0 (once ever) | Baseline diagnostic + setup |
| 1–4 | Block training at full load |
| 5 | **Test + deload week**: weekday load drops to minimum-viable days Mon–Wed; Thu evening or weekend: re-run `diagnostic.html` (~60 min), paste the "Copy result row" line into `tracking.tsv`; Fri: read the delta table against noise thresholds and select the next block. Monthly authentic-audio check also lands here. |

Deload rationale: the diagnostic costs a full session's time, and running it fatigued or crammed contaminates the one measurement the whole system depends on. Quarterly (every ~3rd cycle), week 5 also includes the EF SET external anchor.

**Change rule:** a block "worked" only if its target metric moved **at or above** its noise threshold (ctest ±8, vocab ±1,100, dict ±10, wpm ±12, MTLD ±8). Repeat scores are a *floor*, so a metric that moved up past threshold is real; one that stayed flat is ambiguous, and the monthly authentic-audio check (novel material every time) is the tiebreaker for the decode domain.

### Block selector — explicit mapping from the baseline profile

Priority order where several apply: **decode → automatization → activation → range → use** (perception is upstream of everything).

| Profile from diagnostic | Signature in the numbers | Block assigned |
|---|---|---|
| **Decode-limited** | `dict_pct` low or speed ceiling ≤ 1.0×; authentic-audio < 85%; `ctest_pct`/`vocab_size` fine | **Block A — Perception + Decode** |
| **Knowledge–access gap** | `ctest_pct` and `vocab_size` solid; `wpm` low, `ei_pct` low, high filler/self-repair | **Block B — Automatization** |
| **Receptive–productive split** | `dict_pct` and `vocab_size` high; *all* speaking metrics low | **Block B**, interaction-heavy variant: three conversations/week, 4/3/2 every training day |
| **Passive vocabulary** | `vocab_size` high; `beyond_core_pct` low | **Block C — Lexical Activation**: production-format retrieval of known words + forced-use speaking tasks |
| **Fluent-but-thin** | `wpm` fine; `mtld` and `beyond_core_pct` low | **Block C, range variant**: narrow reading/listening feeds new chunks; paraphrase-constraint tasks |
| **Use-constrained** | Test metrics acceptable; `evidence_n` low | **Block D — Interaction/Wild**: missions with strangers, more human conversations |
| **Flat / no dominant weakness** | Everything mid | Default sequence **A → B** |

A block type repeats at most twice consecutively; if its metric hasn't crossed threshold after two cycles (10 weeks), the drill mix is the problem — switch blocks and raise the interaction share.

## 3. Weekly template within a block

Evening anchor is deliberately the heaviest and holds memory-dependent work (sleep consolidation).

### Example Block A — Perception + Decode (5 weeks)

| Day | Morning (15 min) | Lunch (10–15 min) | Evening (20–30 min) | Total |
|---|---|---|---|---|
| Mon | HVPT set 1 (15) | Narrow listening w/ transcript check (15) | Shadow sandwich ×1 passage (15) + chunk SRS aloud (10) | 55 |
| Tue | HVPT set 2 (15) | Micro-dictation drill (10) | **AI voice conversation, decode brief** (20) + chunk SRS aloud (5) | 50 |
| Wed | HVPT set 1, new voices (15) | Narrow listening (15) | Shadow sandwich (15) + chunk SRS aloud (10) | 55 |
| Thu | HVPT set 2, new voices (15) | Micro-dictation drill (10) | **Tutor session, decode brief** (30) | 55 |
| Fri | HVPT weekly probe: untrained words/voices (15) | Narrow listening (15) | Shadow sandwich (15) + log 3 lines (5) | 50 |
| Sat/Sun (optional) | — | — | Extra narrow listening while attending; one conversation from personal circle | 0–60 |

### Example Block B — Automatization (5 weeks)

| Day | Morning (15 min) | Lunch (10–15 min) | Evening (20–30 min) | Total |
|---|---|---|---|---|
| Mon | Read-aloud warm-up ×3 (5) + **4/3/2 topic X, recorded** (10) | Chunk drill: harvest + rehearse for this week's meetings (10) | **AI voice: task T1, attempt 1** (20) + chunk SRS aloud (5) | 50 |
| Tue | Shadow sandwich (15) | **Pre-meeting rehearsal**: say your two planned contributions aloud (10) → the work meeting itself is the rep | Chunk SRS aloud (10) + narrow listening (15) | 50 |
| Wed | Read-aloud warm-up (5) + **4/3/2 topic X again** (10) | Chunk drill (10) | **AI voice: task T1, attempt 2** — same task, faster, fewer notes (20) | 45 |
| Thu | Shadow sandwich (15) | Prepare tutor tasks (10) | **Tutor: task T1 attempt 3 + free conversation, prompt brief** (30) | 55 |
| Fri | Read-aloud warm-up (5) + **4/3/2 new topic Y** (10) | Chunk drill review (10) | Conversation from personal circle, or AI voice free talk (20) + 5-min log incl. wpm spot-check | 45–50 |
| Sat/Sun (optional) | — | — | One "wild" transactional mission + narrow listening | 0–45 |

Blocks C and D reuse the same grid: C swaps HVPT/4-3-2 slots for production-format vocabulary retrieval from the learner's own passive stock plus paraphrase-constrained speaking tasks; D swaps morning drills down to warm-ups and moves the freed minutes into a third and fourth weekly conversation plus mission prep/debrief.

## 4. Drill specifications

**HVPT / minimal-pair work** (Block A mornings, 15 min). Target selection: every substitution error in the partial-dictation module and the authentic-audio transcription is a candidate contrast — the diagnostic decides, not a stock list. Train 2 contrasts per block. Protocol: 80–100 forced-choice trials per session, immediate right/wrong feedback, ≥4 different voices across the week (rotate TTS voices/accents or a purpose-built HVPT app; never one voice all week). Progression: when Friday's probe (untrained words, untrained voice) ≥ 90% two weeks running, retire the contrast. Material built once on the weekend (10 min), never during the slot.

**Shadow sandwich** (both blocks, 15 min). 60–90-second passage from the narrow-listening topic (same speaker all block). (1) read transcript aloud cold, recorded, 1 pass; (2) listen once; (3) shadow 3 passes, a syllable behind, transcript visible pass 1, hidden pass 3; (4) read aloud once more, recorded. A passage retires after 2 sessions (read-aloud gains concentrate in the first three repetitions).

**4/3/2** (Block B, Mon/Wed/Fri mornings). Topic from a standing list of 8–10 things the learner genuinely talks about. Speak 4 minutes, re-tell in 3, then 2. The shrinking limit is the active ingredient — never relax it; solo delivery to a recorder substitutes for three listeners. Record the 2-minute version; once a week transcribe and compute rough wpm — between-diagnostics telemetry. Same topic Mon and Wed, new topic Fri.

**Chunk drilling** (Block B lunches + both blocks' evening SRS). Harvest, don't import: 8–10 chunks/week from (a) moments stuck in a recording or meeting, (b) the narrow-listening source, (c) the review's conversation-management set. Production-format spaced cards — situation prompt → produce the chunk aloud. New cards drilled to 3 fast correct retrievals, then 1d/3d/7d/21d. Deck cap ~120 live cards.

**Task repetition** (Block B evenings, threaded Mon→Wed→Thu). One communicative task per week — a real one (explain your current project; argue for a decision; tell the story of a problem you solved). Attempt 1 Monday with AI voice, notes allowed; attempt 2 Wednesday, no notes, AI presses with follow-ups; attempt 3 Thursday with the tutor, who does not know it's rehearsed. Expected yield: accuracy and syntactic complexity most, fluency somewhat — which is why 4/3/2 runs in parallel.

**Micro-dictation** (Block A lunches, 10 min): 5 sentences from the narrow-listening source at native speed, two plays each, write, check against transcript — on authentic audio to attack the real-speech penalty the synthetic module hides.

## 5. Interaction placement

Floor in **every** block, including Block A: two conversations/week ≥20 min. Channels: Tuesday evening AI voice (zero-friction, anxiety-cheap — the on-ramp, not the destination), Thursday evening human tutor or exchange (booked for the whole block in week 1), work meetings as uncounted bonus reps, personal-circle conversations as the Friday/weekend option. At least one of the two weekly conversations must be human.

**Standing brief for all interlocutors, AI included:** "Don't fix my sentences. When something breaks, say you didn't understand and make me repair it. Every so often, tell me the three errors I repeated."

**Per-block tutor brief:**
- **Block A:** "Speak at natural speed, don't slow down; I'll summarize back every few minutes and you confirm or say 'not quite' and repeat once at the same speed. Second half: tell me a 2-minute story twice — normal, then fast — and quiz me on details."
- **Block B:** "First 15 min: I re-do a task I've practiced — push me with follow-ups and time pressure. Then free conversation. Prompts only, no reformulations; end with my top-3 repeated errors."
- **Block C:** "Ban my crutch words for the session [list]; when I use one, prompt me to paraphrase. Feed me the natural collocation *after* I've struggled, not before."
- **Block D:** "Rehearse this real upcoming interaction with me [meeting/call/errand], play the difficult version, then debrief where I got stuck."

## 6. Minimum-viable day (≤15 minutes)

One unit, attachable to whichever anchor survives, no equipment beyond a phone:
1. **5 min** — chunk SRS, answers spoken aloud (skipping SRS is the one omission that compounds, so it goes first).
2. **8 min** — one shadow-sandwich passage, short form: read cold ×1, shadow ×2, read ×1 (zero prep — the block's material is pre-cut).
3. **2 min** — voice-memo monologue on today's 4/3/2 topic (keeps the production channel open).
Rule: the MVD counts as a full green day. Two consecutive MVDs are fine; a zero day is not. Week 5 deload days are MVDs by design, so the learner rehearses the fallback every cycle.

## 7. Measurement hooks — the testable predictions

| Block | Should move (prediction) | Should NOT show signal | Falsification / action |
|---|---|---|---|
| **A — Perception+Decode** | `dict_pct` +10 or more; speed ceiling up one step; authentic-audio toward 85% | `wpm`, `vocab_size`, `mtld` | If `dict_pct` < +10 after one cycle *and* authentic-audio flat: rebuild HVPT sets from the new error list; after two cycles, abandon A for B |
| **B — Automatization** | `wpm` +12 or more; `ei_pct` up; fillers and self-repair down | `vocab_size`, `ctest_pct`; `mtld` may even dip (fluency–complexity trade-off is expected) | If `wpm` < +12: check weekly 4/3/2 telemetry — within-session gains but no accumulation → add third conversation, extend B one cycle; no within-session gains → timing discipline broke, audit recordings |
| **C — Lexical Activation / Range** | `beyond_core_pct` up; `mtld` +8 or more; range variant: `vocab_size` +1,100 over two cycles | `wpm` (may dip slightly), `dict_pct` | If speaking-sample lexis flat while SRS accuracy high: transfer failure — shift minutes from cards to forced-use tasks and the crutch-word brief |
| **D — Interaction/Wild** | `evidence_n` up; secondary: `wpm`, `ei_pct` drift up | Test-metric signals not promised — this block buys usage | If `evidence_n` flat: missions too ambitious — halve their size and re-run |

Honesty notes: repeat-run scores are floors, so upward signals are trustworthy and flat ones ambiguous; `ei_pct` is the softest number in the battery — never let it alone decide a block.

## 8. Onboarding (weeks 1–2) and top 3 adherence risks

**Week 1 — measure and rig the environment (no block yet):** Mon evening (or weekend before): run diagnostic end-to-end, rested and honest; copy row to tracking.tsv; save the speaking transcript and dictation error list (raw material for HVPT contrasts, crutch words, first chunks). Tue–Fri: minimum-viable days only — the goal this week is the anchor habit, not load. Also this week: authentic-audio check once for a real-speech baseline; choose the narrow-listening source (transcripts available); pre-cut four shadow passages; build the first HVPT set from dictation errors; create SRS deck with 15 conversation-management chunks; book the tutor for all five Thursdays of cycle 1 with the block brief sent in advance. Fri: read the profile against the §2 table and name Block 1 in writing.

**Week 2 — block starts at ~80% load:** full template with the evening capped at 20 min; first tutor session Thursday; full load from week 3. Week 5 = deload + re-diagnostic.

**Top 3 adherence risks:**
1. **Complexity collapse — ~6 drill types and a 5-week state machine; the likely failure is "I don't remember what today is," which becomes a zero day.** Mitigation: all decisions made once (weekend/week 1) — material pre-cut, HVPT sets pre-built, tutor pre-booked; each weekday cell is a fixed named unit with zero in-slot choices; a one-page block card lives where the learner will see it; the MVD is the universal answer to any confusion.
2. **Boredom of the highest-value drills — HVPT is unadopted "because it is boring," and solo 4/3/2 to a recorder is close behind.** Mitigation: hard caps (HVPT 15 min, never extended; contrasts retire on the 90% rule — visible graduation); drills feed something warm the same week (Monday's 4/3/2 topic is Thursday's tutor task; HVPT contrasts come from the learner's own mishearings); the Friday probe gives a weekly score — progress made visible weekly, not just at week 5.
3. **The interaction floor quietly eroding — solo drills are controllable, conversations are schedulable-away, and anxiety pushes the same direction.** Mitigation: tutor slots block-booked and paid in advance; Tuesday is AI voice precisely because it costs no courage; the weekly log tracks conversations completed above all else — two consecutive weeks below 2 triggers an automatic downgrade of Thursday's requirement to "20 minutes of AI voice," because a kept-small floor beats a broken-large one.
