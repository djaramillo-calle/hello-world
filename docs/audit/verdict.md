# Reconciliation Verdict — English Signal Check audit
Adjudicator: reconciliation of Auditor A (`audit-A.md`) and Auditor B (`audit-B.md`) against `/home/user/hello-world/diagnostic.html` and supporting docs.
Method: every single-source finding and 19 of the 25 convergent findings were re-executed against the shipped code (jsdom 26 harness driving the real page DOM, node v22.22.2; sabotage runs of the author's own test pipeline in a sandbox copy; Monte Carlo of the vocabulary estimator; WCAG luminance computation). Harness and transcripts: `scratchpad/work/{harness.js,t1_flow.js,t2_state.js,t3_speak.js,t4_vocab.js,t5_ctest.js,t6_mc.js,t7_misc.js,sandbox/}`.

Material context for rollout: **`tracking.tsv` contains zero data rows** (header only). Every [COMPARABILITY-BREAKING] fix is therefore free to ship *today*; the tag governs rollout discipline (ship breaking changes together, as one "form v2" bump), not whether to ship.

---

## 1. Merged verdict table

| ID | Finding (one line) | Source | Ruling | Final severity | Comparability | Fix (one line) |
|---|---|---|---|---|---|---|
| U01 | README order Save→Copy emits a blank tracking row (`"2026-08-29\t\t\t\t\t\t\t\t"`) | both (A C1, B C1) | CONFIRMED (executed) | CRITICAL | SAFE | copyRow falls back to last history row; history rows carry all TSV fields (FIX-1) |
| U02 | After saving, `renderReport()` early-returns "Nothing measured yet", hiding history, delta, Copy/Clear; double-save pushes an all-null row | both (A C1, B C3) | CONFIRMED (executed) | CRITICAL | SAFE | Render history/buttons whenever history exists; guard saveSession against empty current (FIX-1) |
| U03 | Delta table compares only the last two *saved* rows — never the session just completed; unreachable at the moment it matters | A only (C2) | CONFIRMED (executed) | CRITICAL | SAFE | deltaNote compares current unsaved session vs last saved row (FIX-1) |
| U04 | `saveSession()` never clears `dictPlays/eiPlays/eiScore/eiSense/evAns`: old answers re-score as new session (EI 100% with zero interaction), Play buttons dead while showing "plays left 2" | B only (C2) | CONFIRMED (executed) | CRITICAL | SAFE | Clear all five state stores in saveSession (FIX-2) |
| U05 | C-test exact-match key rejects valid completions (lie, attribute, moderate, earlier, comforting, tram, several th- slots) | both (A M1, B M4) | CONFIRMED (gaps enumerated; alternates fit stems + maxlength) | MAJOR | BREAKING | Per-gap alternates list (FIX-14) |
| U06 | Curly apostrophes split contractions in `norm()`: +23% word count, −22 MTLD on identical speech; C-test normalizes `’`, speaking doesn't | both (A M8, B M5) | CONFIRMED (executed: 48→59 words) | MAJOR | BREAKING | Normalize `’`→`'` in norm() (FIX-10) |
| U07 | Beyond-core counts regular inflections (things, wanted, friends, walked…) and proper nouns as "lexical reach" | A only (M2) | CONFIRMED (executed against k1set) | MAJOR | BREAKING | Suffix-stripping lookup; optional proper-noun exclusion (FIX-11) |
| U08 | Vocab ±500 "noise threshold" is ≈1σ of a no-change retest difference: 38–43% false "real movement" (graded profile; 14.5% even for an implausibly steep one) | A only (M3) | CONFIRMED (Monte Carlo reproduced 37.9%/42.7%; profile-dependent nuance added) | MAJOR | BREAKING | Raise to ±1,100 (~2σ), document derivation (FIX-16) |
| U09 | Dictation reveals targets on scoring, leaves inputs enabled, silently re-scores — two-click path to unflagged 100% | A only (M4) | CONFIRMED (executed: 0%→paste→100%, no flag) | MAJOR | SAFE | Disable inputs + freeze score after first scoring (FIX-8) |
| U10 | Borrowed psychometrics (α .87–.92, r .82, OPI correlation, 118/142 wpm) presented as this instrument's credentials; all CEFR/coverage/metric cutoffs invented; per-screen bands lack the caveat the docs concede | both (A M5, B M8) | CONFIRMED (all factual anchors verified in source; inference sound) | MAJOR | SAFE | Reword overview/results to attribute figures to the format, caveat every band in-UI (FIX-19) |
| U11 | TTS voice never pinned or recorded (`getVoices().filter(en)[0]`, no `onvoiceschanged`); modules 3–4 are not "identical every run" and drift is undetectable after the fact | both (A M6, B M16-part) | CONFIRMED (code verified; no handler, nothing stored) | MAJOR (adjudicated: A=MAJOR, B=MINOR) | SAFE | Record voice name per session; warn on change (FIX-12) |
| U12 | Test suite asserts nothing (exit 0 under sabotage), tests a local reimplementation of the gate, vacuous duplicates check; METHOD claims a nonexistent dictation test | both (A M7, B M13) | CONFIRMED (sabotage executed: gutted passage → "3 !!!" exit 0; gate deleted → byte-identical output) | MAJOR | SAFE | Real assertions with non-zero exit, test shipped code, add dictation test (FIX-20) |
| U13 | Speaking duration trusted verbatim: secs=5→1200 wpm, −30→−200 wpm, 0→silent 120 substitution; timer decorative | both (A M9c, B M11) | CONFIRMED (executed) | MAJOR | SAFE | Validate secs to [20,600], refuse otherwise (FIX-5) |
| U14 | Degenerate transcripts: 40 fillers → rendered "NaN%"; 300× one word → "Self-repair 199%"; NaN reaches the TSV via copyRow | both (A M9a/b + m9, B M14) | CONFIRMED (executed, incl. literal "NaN" in copied row) | MINOR (adjudicated: pathological input required) | SAFE | Content-word gate, non-overlapping repair count capped ≤1 (FIX-6) |
| U15 | VOID vocab run still stores `size`, drives "Passive vocabulary" diagnosis beside "estimate unreliable", and leaks band-gap sentence + stray `</p>` on the VOID card | both (A M10b, B M6) | CONFIRMED (executed: f=0.375 → size 8000 stored, both notes rendered) | MAJOR | SAFE | Gate diagnose() and both card clauses on `valid` (FIX-7) |
| U16 | Scoring unattempted modules yields confident garbage ("~0 families… trustworthy", EI 0/8, evidence verdict) | both (A M10a, B M17) | CONFIRMED (executed) | MINOR | SAFE | Completeness guards in every score function (FIX-18) |
| U17 | Reload restores "done" tabs with blank forms; one click on Score silently overwrites stored score with 0 | both (A M11, B M18) | CONFIRMED (executed: 0.9→0) | MAJOR (adjudicated: A=MAJOR, B=MINOR — silent destruction of the session's only copy) | SAFE | Confirm-dialog when stored score exists and form untouched (FIX-3) |
| U18 | Ceiling logic `filter().pop()` non-monotone: only-P4 (25% total) → "C1–C2 ceiling"; only sentence 10 → "1.40×" | both (A m1, B M7) | CONFIRMED (executed both scenarios) | MAJOR (adjudicated: A=MINOR, B=MAJOR — UI calls this the most diagnostic number) | SAFE | First-failure semantics (FIX-13) |
| U19 | 8/8 "1000-band" and 7/8 "2000-band" vocab words are inside the tool's own core list; k1 comment says top-1000, list is 1,546, source has 477 dup tokens | both (A m3, B M10) | CONFIRMED (executed) | MAJOR (adjudicated: A=MINOR, B=MAJOR — internal contradiction inflates the exported estimate) | BREAKING | Replace the 7 overlapping 2k words; fix labels (FIX-15) |
| U20 | EI self-rated against a target never shown (rating "exact" uses the faulty channel being measured); fixed sentences memorised by run 2 | B (M9) + A (M5-part) | CONFIRMED (factual: buildEI never displays text; items fixed; inference sound) | MAJOR | BREAKING (reveal) | Reveal sentence after rating; add repeat-exposure caveat (FIX-17) |
| U21 | No doctype/`<html>`/charset/viewport/lang: quirks mode, mojibake risk with multibyte content, 560px media query dead on phones | B only (M12) | CONFIRMED (grep: all four absent; multibyte chars present) | MAJOR | SAFE | Add standard head lines (FIX-9) |
| U22 | Corrupted localStorage primitive (`5`) bricks the page (buildTabs throws, 0 tabs) | B only (M15) | CONFIRMED (executed: TypeError, page dead) | MINOR | SAFE | Type-check S in load() (FIX-4) |
| U23 | Dictation scores reversed word order 100% (contradicts "type exactly what you hear"); 30 stuffed function words score 41% | both (A m12, B M16-part) | CONFIRMED (executed: 100% / 41.1%) | MINOR | SAFE (doc fix chosen) | Disclose order-insensitive scoring in UI (FIX-22) |
| U24 | Plays decremented even when TTS is absent/silent (2 clicks burn both plays, zero audio) | both (A m6, B M16-part) | CONFIRMED (executed with no speechSynthesis) | MINOR | SAFE | Decrement only after successful speak (FIX-23) |
| U25 | Gap construction: 44/80 answers are 1–2 letters, 16/80 are th- completions; METHOD misdescribes construction (words <3 letters silently skipped) | A only (m2) | CONFIRMED (enumerated: 44, 16; code check verified) | MINOR | (redesign) BREAKING / (doc) SAFE | Doc fix now; item redesign WONTFIX for v1 (FIX-28) |
| U26 | Accessibility: no aria-controls/labelledby/pressed, no arrow keys, `--ink-faint` 3.08:1/3.34:1 in light mode, no lang | both (A m4, B M19) | CONFIRMED (DOM + luminance computed; matches both auditors' figures exactly) | MINOR | SAFE | ARIA wiring + darken token (FIX-24) |
| U27 | Dictation `size="52"` input overflows a 360px phone viewport | A only (m5) | CONFIRMED (analytic: ≈450px mono input; corroborated by U21 — no Chromium in this env, A had one) | MINOR | SAFE | Fluid width input (FIX-25) |
| U28 | FILLERS counts only hesitation vocalizations; "like/you know" count as content and inflate wpm | A only (m7) | CONFIRMED (set contents verified; inference reasonable) | MINOR | SAFE | Document limitation (FIX-28); expanding the set WONTFIX |
| U29 | Bank comments overclaim: "half anomalous" is 2/8; dictation "ascending length" is 7,10,11,14,14,13,14,15,15,16 | both (A m8-part, B M21) | CONFIRMED (executed) | MINOR | SAFE | Correct the comments (FIX-28) |
| U30 | History rows omit `beyondRatio` (and eviz yes-count as raw n): `beyond_core_pct` unfillable after save; history table can't show it | both (A m9, B C1-part) | CONFIRMED (code + executed) | MINOR | SAFE | Add fields to history row (FIX-1) |
| U31 | Two-minute timer ends silently; setInterval drifts | A only (m10) | CONFIRMED (code read) | MINOR | SAFE | End-of-timer alarm (FIX-26) |
| U32 | Unrecorded honesty vectors: unlimited unseeded prompt redraws, self-entered duration, self-transcription | both (A m11, B M24) | CONFIRMED (code read) | MINOR | SAFE | Record draw count; warn on timer/duration mismatch (FIX-27) |
| U33 | "Nothing is transmitted" is false — Google Fonts fetched on every load | B only (M20) | CONFIRMED (3 font URLs + footer claim verified) | MINOR | SAFE | Drop remote fonts (local stacks exist) (FIX-21) |
| U34 | The "LCG" isn't one (first product 2.2e16 > 2^53, lossy float recurrence) but shuffle is deterministic and adequately mixed | both (A n1, B M23) | CONFIRMED (executed: overflow + cross-load determinism) | NOTE | SAFE | Fix the comment only (FIX-28) |
| U35 | MTLD faithful to McCarthy & Jarvis except `<=` at exactly 0.72 and zero-factor fallback returning raw token count (300 unique → "300") | both (A n2, B N26) | CONFIRMED (executed) | NOTE | SAFE | Report n/a when factors=0 (FIX-28); `<=` left as-is |
| U36 | Pseudowords `zolvent`/`prantic` (B adds `marlint`) one letter from common words; false-alarm leverage punishes misreads | both (A n3, B M22) | CONFIRMED (judgment; A's 370k-wordlist clean-check covers B's dictionary caveat) | NOTE | BREAKING | Replace zolvent/prantic in the v2 batch (FIX-29); marlint WONTFIX |
| U37 | Gap inputs leak the answer's exact letter count via size/maxlength — absent from the cited C-test forms; maxlength n+3 blocks longer alternates | both (A n4, B M8-part) | CONFIRMED (DOM verified: size=3 maxlength=6 on first gap) | NOTE | BREAKING | Uniform size/maxlength in v2 batch, optional (FIX-30) |
| U38 | BrE spellings (`apologised` spoken by forced en-US voice; `sceptical` in vocab list); apostrophe required inside `practit[ioner's]` gap (curly accepted) | A only (n5) | CONFIRMED with correction (sceptical is never spoken — visual item only) | NOTE | SAFE | METHOD note; otherwise WONTFIX (FIX-28) |
| U39 | Delta of exactly the threshold (+500) is labeled "real movement" while METHOD says "above… is signal" | B only (N25) | CONFIRMED (executed: +500 → "real movement") | NOTE | SAFE | Align doc wording to `>=` (FIX-28) |
| U40 | "Ordered roughly by how much interactional pressure they apply" is just bank order; two compound items | B only (N27) + A caveat-c | CONFIRMED (code: missed list is BANK.eviz.filter — bank order) | NOTE | SAFE | Delete the ordering sentence (FIX-28) |

**Verified non-findings (both auditors, spot-checked):** `esc()` applied at all probed injection points (no XSS); C-test double-score idempotent; vocab gate boundary behaves as coded (9/32 valid, 10/32 void); deterministic shuffle across loads; blocked (as opposed to corrupted) localStorage handled; dark-mode token coverage complete (worst 4.20:1, better than light).

---

## 2. Adjudicated disagreements and contradictions

### 2.1 Vocab validity gate: A-M7 ("30% ceiling never adjudicates") vs B-N29 ("behaves exactly as documented")
Not a behavioral contradiction — resolved by execution: with 32 pseudowords, f takes only values k/32; 9/32 = 0.281 → valid, 10/32 = 0.3125 → void; f can never equal 0.30. The *gate* works as coded (B is right); the *suite's* test inputs f=0.29/0.30/0.31 are unreachable, so the suite adjudicates nothing (A is right, and that point is folded into U12). Both stand.

### 2.2 MTLD zero-factor fallback: A ("reasonable") vs B ("should be flagged undefined")
Behavior agreed and reproduced (300 unique tokens → MTLD "300", growing with length). Judgment split ruled for B, weakly: a value that equals sample size is not a diversity measure; report "n/a" when factors = 0. NOTE-level; part of FIX-28.

### 2.3 Apostrophe magnitudes: A "+20% words" vs B "+12 wpm / −8.8 MTLD"
Different fixtures, not a contradiction. My own fixture: 48 → 59 words (+23%), MTLD 58.6 → 36.2 (−22.4), beyond-core also shifts. Every reproduction is directionally identical and exceeds the instrument's own noise thresholds. U06 CONFIRMED at MAJOR.

### 2.4 Severity disagreements (final calls)
- **U11 TTS voice (A MAJOR / B MINOR) → MAJOR.** A silent, retroactively undetectable stimulus change on two modules of an instrument whose entire validity argument is "identical every run" is a validity threat, not polish.
- **U17 reload zeroing (A MAJOR / B MINOR) → MAJOR.** One unconfirmed click destroys the only copy of a session score, which can then be saved to history as 0.
- **U18 ceiling (A MINOR / B MAJOR) → MAJOR.** The UI explicitly tells users the ceiling is "more diagnostic than the overall percentage"; a 25% run printing "C1–C2" is a wrong headline statistic (reproduced).
- **U19 band overlap (A MINOR / B MAJOR) → MAJOR.** The bottom quarter of an exported number measures the same construct twice, contradicting the tool's own word list — beyond the "approximate bands" disclaimer.
- **U14 NaN/199% (A within MAJOR / B MINOR) → MINOR**, because the trigger inputs are pathological; the realistic half of A-M9 (duration) is split out as U13 at MAJOR.
- **U16 unattempted-module scoring (A within MAJOR / B MINOR) → MINOR.** Requires scoring a form the user knows is empty; wrong text, limited consequence. The VOID-leak half of A-M10 is split out as U15 at MAJOR.
- **U03 delta timing → CRITICAL** (single-source A, reproduced end-to-end): the "Change since last session" table — the tool's stated purpose — is provably never visible with correct data at the moment the README's workflow produces it.

### 2.5 Auditor line numbers
A's line references are offset in places (e.g. "line 198" for the overview table, actually 397). Every checked claim matched the code at the nearby true location; no ruling affected.

---

## 3. Ordered fix specification (implement verbatim, in this order)

### Phase 0 — correctness and data loss
**FIX-9 [SAFE] (U21) Standard head.** At the top of `diagnostic.html`, before `<title>`, add:
`<!doctype html><html lang="en">`, `<meta charset="utf-8">`, `<meta name="viewport" content="width=device-width, initial-scale=1">`. Correct behavior: standards mode, guaranteed UTF-8, live 560px media query on phones, `lang` for assistive tech.

**FIX-1 [SAFE] (U01+U02+U03+U30) Save/copy/report/delta rework.**
1. In `saveSession()`, extend the history row with `beyond: c.speak ? c.speak.beyondRatio : null` and `evyes: c.eviz ? c.eviz.yes : null`.
2. Add at the top of `saveSession()`: if none of `["ctest","vocab","dict","ei","speak","eviz"]` is present on `S.current`, `alert("Nothing to save yet."); return;` (kills double-save null rows).
3. Extract the row-building in `copyRow()` into `rowFields(src)` that accepts either a current-session object or a history row (mapping history fields `ctest/vocab/dict/ei/wpm/mtld/beyond/evyes` to the same 9 TSV columns). `copyRow()` uses `S.current` when it has ≥1 scored module, else the last history entry; if neither exists, alert and return. Any non-finite numeric renders as `""`, never `"NaN"`.
4. In `renderReport()`, delete the `if (!done.length) … return;` early return. Instead: when `done.length === 0`, render the "Nothing measured yet" card in place of the domains grid only; always render the Save/Copy/Clear button row (Save disabled when current is empty), the History table when `S.history.length > 0`, and the delta table per (5).
5. Rewrite `deltaNote()`: `now` = the row built from `S.current` if it has ≥1 scored module, else `S.history[len-1]`; `then` = `S.history[len-1]` when `now` came from current, else `S.history[len-2]`; return `""` only when `then` is undefined. Correct behavior after: README order Save→Copy yields the saved session's data; the profile after saving still shows history and the delta of the just-saved session vs the previous one; a run-2 in progress shows its delta vs run-1 *before* saving.

**FIX-2 [SAFE] (U04) Clear module state on save.** In `saveSession()`, before `buildAll()`:
`[dictPlays, eiPlays, eiScore, eiSense, evAns].forEach(o => Object.keys(o).forEach(k => delete o[k]));`
Correct behavior: after saving, EI/evidence score 0-attempted (and are refused by FIX-18), `#ei-prog` reads "0 / 8", Play buttons actually play with full play counts.

**FIX-3 [SAFE] (U17) Overwrite guard.** In `scoreCtest`, `scoreDict`, `scoreVocab`, `scoreSpeak`: when `S.current.<module>` exists and the form is untouched (all inputs empty / no `data-on="1"` toggles / empty transcript), show `confirm("A saved score exists for this module but the form is empty (page reloaded?). Scoring now overwrites it with 0. Continue?")` and return unless confirmed. Correct behavior: reload + Score prompts instead of silently zeroing 90% → 0%.

**FIX-4 [SAFE] (U22) Storage type guard.** In `load()`, after `S = JSON.parse(raw)`: `if (typeof S !== "object" || S === null || Array.isArray(S)) S = { current: {}, history: [] };` Correct behavior: any corrupted value yields a fresh working page.

**FIX-5 [SAFE] (U13) Duration validation.** In `scoreSpeak()`: `const secs = Math.round(+document.getElementById("sp-secs").value); if (!Number.isFinite(secs) || secs < 20 || secs > 600) { alert("Enter the real duration in seconds (20–600)."); return; }` — delete the `|| 120` fallback. Correct behavior: 5, 0, −30 and blank are refused; wpm can never be negative or >600-range absurd.

**FIX-6 [SAFE] (U14) Degenerate-transcript guards.** In `scoreSpeak()` after computing `content`: `if (content.length < 20) { alert("Too little content after removing fillers — record a fuller sample."); return; }`. Replace the two repair loops with a non-double-counting pass: maintain `const counted = new Set();` unigram loop adds `i` when counting; bigram loop counts only when neither `i` nor `i-1` is in `counted`, then adds both. `repRatio = reps / content.length` is now ≤ 1. Correct behavior: no NaN anywhere; "Self-repair" ≤ 100%.

**FIX-7 [SAFE] (U15) VOID containment.** In `scoreVocab()`'s result HTML, move the `firstGap` ternary (and its closing `</p>`) inside the `!valid ? "" : (…)` coverage clause so a VOID card renders only the void explanation. In `diagnose()`, change the passive-vocabulary condition to `c.vocab && c.vocab.valid && c.vocab.size >= 5000 && …`. Correct behavior: a discarded run leaks no band diagnosis, no malformed HTML, and never triggers "Passive vocabulary."

**FIX-8 [SAFE] (U09) Freeze dictation after scoring.** In `scoreDict()`: first line `if (S.current.dict) return;`; after scoring, `document.querySelectorAll("#dc-holder input").forEach(i => i.disabled = true);`. Correct behavior: identical to the C-test's contract — answers revealed only once inputs are frozen; re-scoring requires Clear, which deletes the stored score.

### Phase 1 — measurement validity (comparability-safe)
**FIX-12 [SAFE] (U11) Pin/record the TTS voice.** In `speak()`: keep a module-level `lastVoiceName`, set to `u.voice ? u.voice.name : "system-default"` on each call; add `window.speechSynthesis.onvoiceschanged = () => {};` warm-up handling at init so `getVoices()` is populated. In `scoreDict()` and `scoreEI()`, store `voice: lastVoiceName` in the result; carry it into history rows; in `renderReport()`/`deltaNote()`, when the voice of the compared sessions differs, append: "Audio voice changed (X → Y) — dictation/repetition deltas are not comparable this round." Correct behavior: voice drift is recorded and flagged, never silent.

**FIX-13 [SAFE] (U18) Monotone ceilings.** In `scoreCtest()`: `let ceiling = null; for (const x of perPassage) { if (x.score / x.of >= 0.6) ceiling = x; else break; }`. Same in `scoreDict()` over `rows` with the 0.8 criterion for `fast`. Correct behavior: only-P4-correct → "below A2–B1"; only-sentence-10 → "not reached". (Ceiling is not a tracked TSV metric, hence SAFE.)

**FIX-18 [SAFE] (U16) Completeness guards.** `scoreVocab`: if 0 items marked → `alert("Mark the words you know first."); return;`. `scoreEI`: if `Object.keys(eiScore).length === 0` → alert+return. `scoreEviz`: if `Object.keys(evAns).length === 0` → alert+return. `scoreDict`: if all inputs empty → confirm before scoring. Also delete the "good discipline; the estimate is trustworthy" clause when fewer than 8 real words were marked (render a neutral "very little was marked — the estimate is a floor" instead). Correct behavior: no unattempted module produces a confident verdict.

**FIX-23 [SAFE] (U24) Plays consumed only on audio.** `speak()` returns `false` in the no-speechSynthesis branch (after the alert) and `true` after `speechSynthesis.speak(u)`. `playDict`/`playEI` decrement and update the counter only when `speak(...)` returned true. Correct behavior: a browser without TTS burns no plays.

### Phase 2 — measurement validity (comparability-breaking; ship together as one "form v2" bump; cost is zero today because tracking.tsv is empty)
**FIX-10 [BREAKING] (U06) Apostrophe normalization.** `const norm = s => s.toLowerCase().replace(/[’‘]/g, "'").replace(/[^a-z0-9'\s]/g, " ").replace(/\s+/g, " ").trim();` Correct behavior: identical transcript scores identically regardless of keyboard; verified fixture: curly and straight both yield 48 words.

**FIX-11 [BREAKING] (U07) Lemmatized beyond-core lookup.** Add
`function coreHas(w){ if (BANK.k1set.has(w)) return true; const cands=[w.replace(/'s$/,""), w.replace(/ies$/,"y"), w.replace(/es$/,""), w.replace(/s$/,""), w.replace(/ed$/,""), w.replace(/ed$/,"e"), w.replace(/ing$/,""), w.replace(/ing$/,"e"), w.replace(/([a-z])\1(ed|ing)$/,"$1")]; return cands.some(b => b !== w && BANK.k1set.has(b)); }`
and use `content.filter(w => !coreHas(w))` for `beyond`. Correct behavior: "walked/friends/things/wanted/working/houses/goes/says/makes/started" are core; "told/said/went" remain core; the beyond list shows genuinely off-list lexis. (Proper-noun exclusion deliberately omitted — `norm()` lowercases; not implementable without retokenizing raw text; documented as a limitation in METHOD.)

**FIX-14 [BREAKING] (U05) C-test alternates.** Add `BANK.ctestAlts = { "0:<gi>": [...], ... }` keyed `"<passageIndex>:<gapIndex>"`, containing at minimum: P1 `tra[in]` +`"m"`; P1 `stre[ets]` +`"ams"`; P2 `att[ach]` +`"ribute"`; P2 `ear[ly]` +`"lier"`; P3 `li[ve]` +`"e"`; P3 `mod[est]` +`"erate"`; P3 `comfor[table]` +`"ting"`; plus, for each of the 16 `th[…]` gaps, whichever of `is/at/ese/ose` completions read grammatically in context (enumerate at implementation; err toward accepting). In `scoreCtest()`: `const ok = val === ans || (BANK.ctestAlts[pi + ":" + gi] || []).includes(val);` and render accepted alternates as `ok`. Chosen over B's replace-the-gaps alternative because it preserves the passages and can only credit more, keeping the change auditable. Correct behavior: "the certainty they attribute", "mistakes lie", "a moderate threshold", "arrives earlier" all score correct.

**FIX-15 [BREAKING] (U19) De-overlap the 2k band + fix labels.** Replace `careful, forest, guard, ocean, prison, silver, wonder` in `BANK.vocab.bands[2000]` with seven words verified programmatically to be absent from `BANK.k1set` and plausibly 2k-frequency (candidates: `blanket, ladder, pigeon, cellar, gravel, spade, drown` — implementation must assert `!BANK.k1set.has(w)` for each in the test suite). Change the k1 header comment from "top-1000" to "~1,500 high-frequency (deduplicated from a longer seed list)". Correct behavior: no vocab band item appears in the core list (asserted by FIX-20's suite); UI label, comment, and list agree.

**FIX-16 [BREAKING] (U08) Honest vocab noise threshold.** In `deltaNote()`, change `cmp("Vocabulary", …, 500)` to `1100`. Update the threshold tables in `docs/METHOD.md` and the `tracking.tsv` header comment to `vocab +/-1100`, and add one derivation sentence to METHOD: "single-administration SD ≈ 250–400 families (8 items/band binomial), so a between-session difference has SD ≈ 350–570; the threshold sits at ~2σ." Correct behavior: a no-change learner is flagged "real movement" a few percent of the time, not ~40%.

**FIX-17 [BREAKING] (U20) Anchor EI self-rating.** In `pickEI(i, v, btn)`, after setting the rating, reveal the target once: if `#et-<i>` does not exist, insert `<div class="itemno" id="et-<i>">target: <sentence text></div>` under item i. Add to the EI result card and METHOD.md: "The eight sentences are fixed; by the second or third run you will partly remember them — treat repeat EI scores as a floor, more so than any other module." Correct behavior: the 0–4 rating is made against the visible target instead of the memory channel being measured; the familiarity threat is disclosed. (Item rotation explicitly deferred — out of v1 scope.)

**FIX-29 [BREAKING, optional] (U36) Pseudoword hygiene.** Replace `zolvent` and `prantic` with phonotactically legal strings ≥2 edits from any common English word (implementation must check candidates against a wordlist; e.g. `zorvale`, `prundic`). `marlint` stays (WONTFIX — containing "marlin" is not edit-distance-1 confusability).

**FIX-30 [BREAKING, optional] (U37) Remove the letter-count hint.** Give every gap input `size="8"` and a uniform `maxlength="12"` (also unblocks longer alternates from FIX-14). Correct behavior: input width no longer discloses answer length, matching the cited C-test forms' presentation.

### Phase 3 — honesty of claims
**FIX-19 [SAFE] (U10).**
1. Overview C-test row: "α ≈ .87–.92; parallel forms r ≈ .82. Highest reliability per minute of any format." → "The *format* reports α ≈ .87–.92 and parallel-forms r ≈ .82 in published, piloted versions; these home-made passages inherit the format, not those figures."
2. EI row: append "…in rater-scored versions; this module is self-rated."
3. `scoreCtest` result card and report metric: append "(uncalibrated author mapping — ±1 CEFR sub-level at best)" wherever `ctBand()` output is printed.
4. `rateNote`/report: change "(~142 wpm in corpus studies)" phrasing to make clear the 118/142 figures are group means from interview corpora, computed from audio with fillers included, and that this tool's pruned self-timed wpm is not the same measure — "reference points, not cutoffs."
5. Dictation card: "Below 1.15× means normal conversational speed…" → "Rates are multiples of this device's synthetic voice; they are comparable across your own sessions on the same device/voice, not across devices."
6. Speaking metric detail strings: mark MTLD 70/45, filler 8%, self-repair 5%, beyond-core 22%/14% as "author guesses, untested" (one shared footnote line in the results card is sufficient).
7. METHOD.md: fold these same attributions into §1/§5; the "Calibration honesty" section's concession must appear at first mention of any borrowed figure.
Correct behavior: no screen presents another instrument's statistics as this instrument's credentials.

**FIX-20 [SAFE] (U12) Real test suite.** Rewrite `scripts/tests.js`/`run-tests.js`:
1. Every check is an assertion; any failure sets `process.exitCode = 1` and prints FAIL.
2. Gap counts: assert `=== 20` per passage.
3. Validity gate: drive the *shipped* logic (load the page in jsdom, or export the pure scoring functions) with reachable inputs — assert 9/32 alarms → valid and 10/32 → void; delete the local `sim()` reimplementation.
4. Dictation: assert `tokenOverlap` full credit on exact match, the curly-apostrophe case (post-FIX-10: `don’t` ≡ `don't`), and partial credit counts.
5. Item-bank integrity: assert no `BANK.vocab.bands` word is in `BANK.k1set` (locks FIX-15); assert pseudoword list disjoint from bands; duplicates check runs on the raw source string or is deleted.
6. MTLD: assert expected values for two fixed sequences (±0.1).
7. Regression tests for FIX-1/2/5/6/7/8 behaviors (jsdom).
Update METHOD.md's "Running the tests" to describe what is actually checked. Correct behavior: the sabotages performed in this adjudication (gutted passage; deleted gate) make the suite exit non-zero.

**FIX-21 [SAFE] (U33) Make the privacy line true.** Delete the three Google Fonts `<link>`s (the declared fallback stacks — Helvetica/Arial, Georgia, Menlo/monospace — remain). Footer line stays as-is and is now true; alternatively (if the typefaces must stay) change the footer to "Results never leave this browser; the page requests fonts from Google." The first option is chosen: offline-capable and claim-true.

**FIX-22 [SAFE] (U23) Disclose dictation scoring.** In the dictation result card, add: "Scored by word overlap, ignoring order and punctuation." Keep the instruction "Type exactly what you hear" (it elicits the right behavior even though scoring is lenient); METHOD already documents this.

**FIX-28 [SAFE] (U25-doc, U28, U29, U34, U35, U38, U39, U40) Doc/text corrections, one commit.**
- METHOD.md C-test construction: "the second half of every second word **of three or more letters** is deleted; the first sentence of each passage is left intact; 20 gaps per passage."
- METHOD.md new limitation note: filler measure counts hesitation vocalizations only (um/uh/er family); lexical fillers (like, you know) count as content.
- `BANK.ei` comment: "Half the items" → "Two of the eight items are semantically anomalous". `BANK.dict` comment: "ascending length and rate" → "ascending rate; length roughly ascending".
- Shuffle comment: "Deterministic shuffle" — replace the LCG constants claim with "deterministic float-recurrence shuffle (not a modular LCG — products exceed 2^53 — but stable across platforms; mixing verified)".
- `mtld()`: `return factors > 0 ? toks.length / factors : null;` and render "n/a" (the existing `md === null` path already handles it).
- METHOD.md/tracking.tsv threshold wording: "movement **at or above** the threshold counts as signal" (matches the `>=` code).
- Delete the sentence "They are ordered roughly by how much interactional pressure they apply." from `scoreEviz()`.
- METHOD.md note: item spellings are BrE (`sceptical`, `apologised`, `judgement`) while the synthetic voice is en-US; `apologised` is spoken with US pronunciation.

### Phase 4 — polish
**FIX-24 [SAFE] (U26) Accessibility.** Tabs: `id="tab-<mod>"`, `aria-controls="p-<mod>"`; panels: `aria-labelledby="tab-<mod>"`; ArrowLeft/ArrowRight/Home/End keyboard handler on the tablist; roving tabindex. All toggle buttons (`toggleYN`, `pickSense`, `pickEI`, `pickEv`): set `aria-pressed` alongside `data-on`; vocab buttons get `aria-label="know: <word>"`. C-test ok/bad: add `aria-invalid="true"` on bad. Light-mode `--ink-faint`: `#838C88` → `#6C7570` (4.59:1 on panel — computed). Correct behavior: WCAG AA text contrast, screen-reader-legible state on all 96+ toggles, keyboard-operable tabs.

**FIX-25 [SAFE] (U27) Fluid dictation input.** Replace `size="52"` with `style="flex:1 1 200px;min-width:0;max-width:460px"` (btnrow already flex-wraps). Correct behavior: no horizontal page scroll at 360px (with FIX-9's viewport meta making that width real).

**FIX-26 [SAFE] (U31) Timer alarm.** When `spLeft <= 0`: set the timer text to "0:00", add a `.timer-done` class (high-contrast flash animation), call `navigator.vibrate && navigator.vibrate(200)`, and play a short WebAudio beep (oscillator, ~200 ms; wrapped in try/catch). Correct behavior: the end of the two minutes is perceivable without watching the screen.

**FIX-27 [SAFE] (U32) Record honesty context.** Count prompt draws (`spDraws++` in `drawPrompt`, reset in `buildSpeak`); store `draws: spDraws` in `S.current.speak`; if the timer was last run and `|secs − timed duration| > 15`, render a one-line note "entered duration differs from the timed run." Display "prompt draws: n" in the result card. Correct behavior: prompt-shopping and duration mismatch are visible in the record, aligned with the vocab module's distrust-by-design.

### Confirmed but WONTFIX (explicit)
- **U25 item redesign** (too many 1–2-letter/th- gaps): redesigning gaps is a new form — deferred; only the documentation misdescription is fixed (FIX-28). Rationale: the defect lowers efficiency, not correctness, and a redesign belongs with a deliberate v2 form, not this remediation.
- **U28 filler-set expansion**: counting "like/you know" as fillers needs disambiguation from legitimate uses ("I like it", "you know the answer") that a token matcher cannot do; documented as a limitation instead.
- **U36 `marlint`** and **U38 BrE/US register mix**: below the harm threshold; documented.
- **U34 LCG arithmetic**: behavior is correct-by-luck but verified deterministic and well-mixed on the only platforms that matter (IEEE-754); only the comment is corrected. Replacing the generator would be comparability-breaking for zero measurement benefit.

---

## 4. Rulings on report-level claims

**Auditor A's three most-confident findings — all hold.**
1. C1: reproduced byte-for-byte (`"2026-08-29\t\t\t\t\t\t\t\t"` after Save→Copy; report blanks; Copy button gone).
2. M2: reproduced (`things/wanted/working/friends/houses/asked/walked/goes/says/makes/started` all absent from k1set; `told/said/went` present).
3. M7: reproduced by identical sabotage (gutted passage → "passage 4: 3 !!!" with exit 0; gate deleted → byte-identical suite output; baseline output matches the shipped verification log).

**Auditor B's three most-confident findings — all hold.**
1. CRITICAL 1: as above.
2. CRITICAL 2: reproduced end-to-end (EI 100% re-scored with zero interaction post-save; `#ei-prog` "8 / 8"; Play dead with "plays left 2" displayed).
3. MAJOR 4: gap enumeration reproduced via the shipped `gapText`; all claimed alternates exist and fit their `maxlength` caps.

**"Could not verify" caveats — do any change a ruling? No.**
- *Literature figure transcription* (both): still unverified here (no source-paper access). Immaterial: U10 rests on provenance (figures measured on other, piloted instruments), not transcription accuracy — both auditors framed it that way, and I concur. B's partial verification that the 118/142 wpm figures are interview-corpus group means *strengthens* U10.
- *Real TTS behavior* (both): unverifiable in this environment as well. U11/U24 rulings rest entirely on code-level facts (voice-selection expression, no `onvoiceschanged`, decrement-before-speak), which I verified; the Chrome `cancel()`/`speak()` race in B-M16 remains an unverified sub-claim and is not load-bearing for any ruling.
- *Clipboard on `file://`* (A): the `prompt()` fallback exists in `copyRow()` and is code-verified; no finding depends on it.
- *A's caveat on the evidence-ordering claim*: resolved — B verified (and I confirmed in code) that the "ordered by interactional pressure" list is plain bank order → U40 CONFIRMED.
- *B's pseudoword-dictionary caveat*: resolved by convergence — A ran the 370k-wordlist check B couldn't; U36's factual base stands.
- *A's exact 461px/481px mobile measurements*: not reproducible here (no Chromium); the substance (≈450px fixed-width input vs 360px viewport) is arithmetic and stands (U27).

---

## 5. Counts

| | |
|---|---|
| Unified findings | **40** |
| CONFIRMED | **40** |
| REJECTED | **0** |
| UNRESOLVABLE | **0** (three non-load-bearing *sub-claims* noted as unverifiable in §4) |
| Convergent (both auditors) | **25** — 19 spot-checked by execution (mandate minimum: 9) |
| Single-source | **15** (A: 9 — U03, U07, U08, U09, U25, U27, U28, U31, U38; B: 6 — U04, U21, U22, U33, U39, U40) — all 15 reproduced or factually verified before confirmation |
| Final severities | 4 CRITICAL / 15 MAJOR / 14 MINOR / 7 NOTE |
| Confirmed-but-WONTFIX | 4 (U25-redesign, U28-expansion, U36-marlint, U34-generator; each with doc-level remediation in FIX-28) |
| Comparability | 8 findings require BREAKING fixes (U05, U06, U07, U08, U19, U20, U36, U37) — all free to ship now: tracking.tsv holds zero data rows |

Both audits were of unusually high quality: every mechanically checkable claim in both reports reproduced exactly (down to byte-identical clipboard output, the 199% self-repair figure, the 3.08:1/3.34:1/4.45:1 contrast ratios, and the 44/16 gap-distribution counts). The two reports contradict each other nowhere on facts; all apparent tensions were framing or severity, adjudicated in §2.
