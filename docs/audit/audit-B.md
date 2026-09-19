# AUDIT REPORT — English Signal Check (`/home/user/hello-world/diagnostic.html`)

Method: extracted both `<script>` blocks and drove the full page in jsdom (real DOM, stubbed TTS/clipboard/storage) under node v22.22.2. Every finding below was reproduced by executing the actual shipped code unless marked otherwise. Test harness and fixtures are in the scratchpad (`harness.js`, `t1_gaps.js` … `t9_diag.js`).

## CRITICAL

**[CRITICAL 1] The documented tracking workflow silently produces an empty data row.**
Location: `diagnostic.html` `saveSession()` (lines 1370–1388) + `copyRow()` (lines 1390–1407); `README.md` step 1 ("Hit *Save this session to history*, then *Copy result row* and append the line to `tracking.tsv`").
`saveSession()` sets `S.current = {}` (line 1383). `copyRow()` reads exclusively from `S.current`. So following the README's order emits a row with a date and eight empty fields.
Verified (t6_state.js): after completing C-test (100%) and speaking, copyRow **before** save → `"2026-08-29\t100\t\t\t\t60\t7.1\t100\t"`; copyRow **after** save (README order) → `"2026-08-29\t\t\t\t\t\t\t\t"`. Worse, after saving, the Copy button is not even reachable (see CRITICAL 3), so the user pastes the blank they copied or nothing. The entire repo exists to accumulate `tracking.tsv`; its documented path destroys the data with no warning.
Fix: build the row from the saved history entry (or snapshot `S.current` before clearing), and/or have `saveSession()` trigger the copy; at minimum swap the README order and store `beyondRatio` in history (it is currently only recoverable via copyRow, so the `beyond_core_pct` column is unfillable after a save).

**[CRITICAL 2] Stale module state after saving a session lets old scores be silently re-recorded as new measurements.**
Location: `saveSession()` calls `buildAll()` (line 1386), but the answer stores `dictPlays` (line 952), `eiPlays/eiScore/eiSense` (line 1036), `evAns` (line 1210) are only cleared by each module's own `reset*()`, never by `saveSession()`.
Verified (t6_state.js): rate all 8 EI items 4/4, score (100%), save session; then click "Score this module" with zero interaction → EI scores **100% again** into the new session; `#ei-prog` already reads "8 / 8". Same for evidence (14/14 reproduced). Dictation/EI Play buttons are dead in the new session while the UI shows "plays left 2" (`playDict` reads exhausted `dictPlays`, verified: no utterance spoken, counter display reset by `buildDict` but not the store). For a change-tracking instrument, carrying last session's answers into the next session unnoticed is data corruption, and the dead Play buttons make the modules unrunnable without a manual Clear.
Fix: clear all four state objects in `saveSession()` (or in each `build*()`).

**[CRITICAL 3] After saving, the Profile tab hides all history, the delta table, and the Copy/Clear buttons.**
Location: `renderReport()` lines 1261–1269: `if (!done.length) { holder.innerHTML = "Nothing measured yet…"; return; }` — the early return fires precisely when a session was just saved (current cleared, history non-empty).
Verified (t8_report.js): complete C-test → save → `renderReport()` → "Nothing measured yet. Run at least the C-test…", `History` table absent, `rp-when` = "no modules run yet". Your entire measurement history is invisible exactly at the moment the README tells you to record it, and stays invisible until you complete a module of the *next* session. Also verified: double-clicking "Save this session" pushes a second all-null row (`{ctest:null, …}`) into history, which then suppresses the next delta table (every `cmp` skips on null).
Fix: render history/buttons whenever `S.history.length > 0`; guard `saveSession()` against an empty `S.current`.

## MAJOR

**[MAJOR 4] C-test exact-match key rejects correct English — ~7 of 80 gaps have alternative valid completions.**
Location: `gapText()` (713–738) + `scoreCtest()` exact comparison `val === ans` (789). I enumerated all 80 gaps by executing `gapText()` (t1_gaps.js) and checked each stem in context:
- P3: "most expensive mistakes **li[ve]**" — "li**e**" ("where mistakes lie") is at least as idiomatic; fits `maxlength` 5. Scored wrong.
- P2: "the amount of certainty they **att[ach]** to something" — "att**ribute**" (6 chars, exactly `maxlength` n+3=6) is fully grammatical and natural. Scored wrong.
- P3: "Beyond a **mod[est]** threshold" — "mod**erate**" fits maxlength 6, fully acceptable.
- P1: "On the **tra[in]** I usually read" — "tra**m**" is equally consistent with "I walk to the station".
- P1 ×2–3: "walk to **th[e]** station", "from **th[e]** small place", P3 "between **th[e]** two" — "th**is**"/"th**at**"/"th**ese**" are grammatical in context and within maxlength.
- P1: "The **stre[ets]** are still quiet" — "stre**ams**" is marginal but grammatical.
METHOD.md sells exact-match as unproblematic; professional C-test practice pilots gaps and keys acceptable variants precisely because of this. A B2+ user loses up to ~9 points (the claimed noise threshold is ±8) for producing *better* English than the key. Fix: accept an alternatives list per gap, or replace the ambiguous gaps (breaking comparability once — better now than never).

**[MAJOR 5] Curly vs straight apostrophes in the transcript move speaking metrics past the instrument's own noise thresholds.**
Location: `norm()` line 967 — `replace(/[^a-z0-9'\s]/g," ")` keeps straight `'` but converts `’` to a space, splitting every contraction ("don’t" → "don","t"). `scoreCtest` normalizes `’`→`'` (line 788); `norm()` does not.
Verified (t5b.js), identical speech typed both ways: curly → 76 words, wpm 76, MTLD 39.6, beyond-core 50.0%; straight → 64 words, wpm 64, MTLD 48.4, beyond-core 53.1%. Deltas: **+12 wpm (= the stated ±12 noise threshold) and −8.8 MTLD (> the stated ±8 threshold) from typography alone.** Phantom tokens "don", "t", "s", "re" also count as "beyond the ~1,500 most frequent" words. Phone-keyboard dictation — the transcription route the tool itself recommends (line 1108) — emits curly apostrophes by default. Fix: `replace(/’/g,"'")` inside `norm()`.

**[MAJOR 6] A VOID vocabulary run still drives the cross-domain diagnosis, and the VOID card renders contradictory dangling text.**
Location: `scoreVocab()` stores `size` regardless of validity (line 892); `diagnose()` line 1330 checks `c.vocab.size >= 5000` with no `valid` check. Verified (t9_diag.js): f = 0.375 (run declared "discarded rather than reported") stores size 8000 and the report prints "**Passive vocabulary.** You recognise a large vocabulary…" directly above "**Vocabulary estimate unreliable.**" Second bug, same function: on a VOID run the result card appends the band-gap sentence unconditionally (line 903 ternary is outside the `!valid ? "" :` guard) — verified output: "VOID … this run is discarded … **Knowledge starts thinning at the 1,000 band** — that is where deliberate vocabulary work has the most room", with an orphaned `</p>`. Fix: gate both on `c.vocab.valid`.

**[MAJOR 7] Ceiling logic reports the last passing item, ignoring failures below it — in both C-test and dictation.**
Location: `scoreCtest()` line 803 and `scoreDict()` line 988, both `filter(...).pop()`.
Verified: pass passages 1 and 3, fail 2 and 4 → "ceiling **B2–C1**" (t2_ctest.js case C). Dictation: correct only sentence 10, everything else blank (12% overall) → "Speed ceiling **1.40×**" (t4_dict.js case D). METHOD.md's promise — "localises where automatic processing fails" / "the fastest rate still decoded" — is exactly wrong for non-monotone profiles, which are common (a lucky guess or a familiar sentence). Fix: report the highest level below the *first* failure, or require all lower items to also pass.

**[MAJOR 8] Borrowed psychometrics presented as properties of this unpiloted instrument.**
Locations: overview table line 397 ("α ≈ .87–.92; parallel forms r ≈ .82" as the C-test row's credentials), METHOD.md §1, `ctBand()` lines 815–825, `coverageNote()` 909–914, `rateNote` 1181–1186.
- The α/.82/.76 figures belong to published, piloted C-tests (multiple calibrated passages). These four passages were written by the author, never piloted, use exact-match with ambiguous gaps (MAJOR 4), and visually leak answer length (`size=Math.max(n,2)`, `maxlength=n+3` — line 755 — standard C-tests don't tell you how many letters are missing). None of the borrowed reliability transfers.
- `ctBand()`'s seven CEFR cutoffs (25/40/55/68/78/86/93%) are invented: C-test percentage depends entirely on passage difficulty, so a %→CEFR mapping without external anchoring is fabricated precision — while the docs elsewhere concede ±1 sub-level, the UI still prints "Provisional band: **B2**".
- wpm 118/142: these are real means from Huang & Gráf's LINDSEI/LOCNEC study — but they are **group means from interview/picture-description corpus data**, computed from audio, used here as individual cutoffs (`conf: wpm>=118 ? "high"`) on a self-timed, self-transcribed monologue whose word count *excludes* fillers (line 1164, a "pruned" rate) — a systematically different measure. Distributions at adjacent CEFR levels overlap heavily; a mean is not a boundary.
- Coverage claims (2k→90%, 3k→95%, 6k→98%) are Nation-style figures for word-family counts from validated tests, attached to a home-made 8-items-per-band estimate whose band assignments are demonstrably wrong (MAJOR 10).
- Noise thresholds (±8, ±500, ±10, ±12, ±8) are asserted in three places with no derivation; ±8 MTLD is especially indefensible given the module accepts 40-token transcripts while McCarthy & Jarvis recommend ≥100 tokens for MTLD stability.
Fix: label all bands/cutoffs as author guesses in the UI itself (not only in METHOD.md), or remove the CEFR/coverage language until the EF SET anchoring the docs recommend has actually produced a personal conversion.

**[MAJOR 9] Elicited imitation is self-rated against a target the rater can no longer inspect — and item memory destroys it by run 2.**
Location: module 4 UI (buildEI, 1021–1034): one play, no text display ever, then self-rate "4 — exact". Rating "exact" requires comparing your utterance to a sentence held only in the memory whose capacity is the construct being measured — the measurement and the criterion are the same faulty channel. METHOD.md's defense ("the rater's generosity is roughly constant across sessions") is an unsupported assumption; rubric drift and increasing familiarity push the opposite way. Worse: the 8 sentences are fixed across runs. EIT works *because* sentences exceed verbatim memory; once the user half-knows "The patient mountain apologised for the crowded silence," reproduction no longer requires grammatical reconstruction. METHOD.md flags item memory for the C-test only — it is far more fatal here. Fix at minimum: reveal the sentence text after rating so the score is anchored; ideally rotate parallel sentence sets, or drop the module's number from the tracked row.

**[MAJOR 10] The vocabulary bands contradict the tool's own frequency list.**
Location: `BANK.vocab.bands` (553–563) vs `BANK.k1` (637). Verified programmatically (t7_items.js): all 8 "1000-band" words and **7 of 8 "2000-band" words** (`careful, forest, guard, ocean, prison, silver, wonder` — everything except `repair`) are inside the author's own ~1,500-word "core/top-1k" list. A word cannot simultaneously be a 2k-band probe and top-1k core. So the bottom quarter of the size estimate measures 1k knowledge twice, inflating low-end estimates, and the "beyond-core" speaking measure treats the same words inconsistently. Also the k1 header comment says "top-1000" while the list contains 1,546 words labeled "~1,500" in the UI.

**[MAJOR 11] Speaking duration is trusted verbatim; wpm is trivially and silently corruptible.**
Location: `scoreSpeak()` line 1154: `+document.getElementById("sp-secs").value || 120`. The `min="20" max="600"` attributes don't constrain typed values. Verified (t5b.js): secs=5 → **1200 wpm**; secs=−30 → **−200 wpm**; both stored, displayed, and saveable to history with no flag. The timer (startTimer) is decorative — nothing connects it to the analysed duration. For the tool's headline metric this is the widest open door to accidental inflation (stopping recording early and leaving 120 in the box deflates; mis-entering inflates). Fix: clamp to [20, 600], warn when the entered duration differs from the last timer run.

**[MAJOR 12] Missing doctype, charset, and viewport: quirks mode, mojibake risk, and dead mobile styles.**
Location: file starts at line 1 with `<title>`; verified by grep there is no `<!doctype>`, `<html>`, `<meta charset>`, or viewport meta anywhere, and the file contains multibyte UTF-8 (`’ — ≈ ·` in test items and passages). Consequences: the page renders in quirks mode; without a charset declaration a browser that falls back to windows-1252 (common for `file://`) corrupts the C-test passages and prompts; and with no viewport meta, phones lay out at ~980px, so the `@media (max-width: 560px)` block (line 368) — the only mobile accommodation — can never match on the devices it targets. The C-test's 80 inline inputs and the 96-tile yes/no grid are the audit's named mobile concerns and both render zoomed-out and untappable. Fix: add the three standard head lines.

**[MAJOR 13] The test suite does not test what METHOD.md says it tests, and the verification log records a suite with almost no assertions.**
Location: `scripts/tests.js`, `scripts/run-tests.js`; METHOD.md "Running the tests": "Checks gap counts, item-bank integrity, the validity gate, MTLD behaviour and dictation scoring."
- **There is no dictation-scoring test at all.** Nothing in tests.js touches `tokenOverlap`, `norm`, or `scoreDict`.
- The "VOCAB VALIDITY GATE" section never calls `scoreVocab()`; it evaluates a locally re-implemented `sim()` with the gate and formula hard-coded (tests.js lines 8–12). It would print the same output if the real gate were deleted.
- "duplicates remaining: 0" checks `BANK.k1.length - new Set(BANK.k1).size` — tautologically 0, because `BANK.k1` was already deduplicated through a Set at line 639.
- "MTLD behaviour" is one printed number with no expected value; the beyond-core section uses its own tokenizer and its own 3-word filler list instead of the engine's `norm`/`FILLERS`.
- Nothing asserts; the process exits 0 regardless (only the gap-count lines carry an "ok/!!!" string that doesn't affect exit code).
I re-ran the author's exact pipeline from a scratch copy: the output matches `logs/verification-2026-08-29.txt` byte-for-byte (one trailing blank line differs). The log is *honest* but it certifies close to nothing: none of the bugs in CRITICAL 1–3 or MAJOR 5–7 could ever be caught by this suite, because it stubs the DOM to `getElementById: () => null` and strips everything after `load();`, excluding every scoring path that reads the DOM.

## MINOR

**[MINOR 14] Pathological transcripts produce NaN and >100% metrics.** Verified (t5_speak.js): 40×"um" → "Self-repair **NaN%**" rendered, `repRatio: NaN` stored in `S.current` (becomes null in history only because `JSON.stringify(NaN)` → null); 300×"cat" → repRatio **1.987**, displayed as "Self-repair 199%" (lines 1161–1162 double-count via the 1-gram and 2-gram detectors). Guard the 0-content and >1 cases.

**[MINOR 15] Corrupted localStorage bricks the page.** If `engsig.v1` contains a JSON primitive (e.g. `5`), `load()` sets `S=5`; `S.current = {}`-repair silently no-ops on a primitive, and `buildTabs()` throws (`Cannot read properties of undefined`), leaving a dead page with no recovery path. Verified (t6_state.js F). Blocked storage, by contrast, is handled fine (verified). Fix: `if (typeof S !== "object" || !S) S = {current:{},history:[]}`.

**[MINOR 16] Dictation is gameable and forgiving in undisclosed ways.** Verified: pasting each target sentence *reversed* scores 100% (order-insensitivity is documented, but "type exactly what you hear" implies order matters); typing the same 30 common function words into all ten boxes scores **41%** with zero listening. Also a play is burned even when TTS produces no audio (voices not yet loaded / `cancel()`-then-`speak()` Chrome race, lines 929–935 — no `onvoiceschanged` handler; `getVoices()[0]` picks an arbitrary English voice which can differ across sessions/devices, undermining the 0.95–1.40× rate comparability the module depends on).

**[MINOR 17] Scoring before answering yields confident garbage.** Vocab with nothing marked → "~0 word families … **good discipline; the estimate is trustworthy**" (conf "high"); evidence with nothing answered → 0/14 "mostly being studied" verdict; EI unanswered → "0/8 meaning judgements correct" as though the user judged wrongly. No module checks completeness before scoring.

**[MINOR 18] Reload restores scores but not answers; re-scoring silently zeroes them.** Verified (t7_items.js): seed storage with a saved 90% C-test, reload → tab shows done, all inputs empty; clicking Score replaces 0.9 with 0, no confirmation.

**[MINOR 19] Accessibility.** Verified from DOM: `role="tab"` buttons with no `aria-controls`, panels with no `aria-labelledby`, no arrow-key tab navigation; the 96 vocabulary toggles and all yes/no/rubric toggles convey state only via `data-on` styling — no `aria-pressed`, so a screen reader hears 96 identical "know" buttons with no word association and no state. `--ink-faint` text (#838C88) computes to **3.34:1** on panel and 3.08:1 on ground at 10–11px (brandline, item numbers, plays-left counters, table headers, "know" idle state) — well under WCAG AA 4.5:1; callout `strong` is 4.45:1. Dark palette is complete and slightly better (4.20:1 worst). No `lang` attribute exists (no `<html>` tag).

**[MINOR 20] "Nothing is transmitted" is false as stated.** Footer line 519 vs lines 2–4: the page requests Google Fonts on every load, transmitting IP/UA to Google. Results are indeed local; the absolute claim isn't.

**[MINOR 21] Item-bank comments overclaim.** `BANK.ei` header: "Half the items are semantically anomalous" — 2 of 8 are (verified). `BANK.dict` header: "ascending length and rate" — word counts run 7,10,11,14,**14,13,14**,15,15,16 (verified); rate ascends, length doesn't. EI syllables do ascend (≈9→22), so METHOD's "ascending length" holds for module 4.

**[MINOR 22] Pseudoword "zolvent" is one letter from "solvent"** (and a pseudo-homophone for L1s with initial s-voicing, e.g. German); "marlint" contains "marlin". A disciplined learner who knows *solvent* can be false-alarmed by misreading, which the design then uses to void their run. The rest of the 32 pseudowords check out as non-words to my knowledge (no system dictionary available — see caveats). Real-word items are all correctly spelled (`sceptical` is BrE, consistent with `judgement/apologised`).

**[MINOR 23] The "deterministic shuffle" is not the LCG it appears to be, but it works.** Line 848: `seed*1103515245` exceeds 2^53 on the first step (verified: `20260829*1103515245 > MAX_SAFE_INTEGER`), so the arithmetic is done in lossy floating point — the recurrence is not the stated LCG. In practice: deterministic across loads (verified, identical order on repeated instantiation), 96 distinct draws spanning [0.004, 0.991], pseudowords well interleaved (longest consecutive run: 4). Fragile-by-luck rather than wrong.

**[MINOR 24] Prompt draw is uncontrolled.** `drawPrompt()` uses unseeded `Math.random` with unlimited redraws; nothing stops re-rolling until a rehearsed topic appears, and nothing records how many draws happened — at odds with "Reading it and starting within five seconds is part of the measurement."

## NOTE

**[NOTE 25]** Delta verdict boundary: `Math.abs(d) >= minMove` marks a move of exactly the threshold (e.g. +500 vocab, verified) as "real movement", while tracking.tsv says movement must exceed noise. One-character semantics; document either way.

**[NOTE 26]** MTLD implementation is otherwise faithful to McCarthy & Jarvis 2010: bidirectional average, 0.72 threshold, partial factor `(1−TTR)/(1−0.72)` — verified against hand computation. Two deviations: factor triggers at TTR **≤** 0.72 (paper's canonical implementations use "drops below"; verified a 25-token sequence hitting exactly 0.72 counts a factor), and a zero-factor text returns raw token count (300 unique tokens → MTLD "300", growing with sample length rather than being flagged undefined).

**[NOTE 27]** Evidence inventory items are genuinely behavioural and mostly well-constructed; two are mildly compound (item 1 conjoins duration with "couldn't have had it in another language"; item 6's "without subtitles and without rewinding" doesn't apply to live meetings). The results page claims the unticked list is "ordered roughly by how much interactional pressure they apply" — it's bank order, and that ordering claim is not defensible (e.g. "wrote something longer than a paragraph" sits between phone calls and storytelling).

**[NOTE 28]** `esc()` is correctly applied at every user-text injection point I could find; XSS attempts through the transcript textarea and dictation inputs were escaped in output (verified with `<img onerror>` payloads in both). `esc()` doesn't escape single quotes, but no user text is interpolated into single-quoted attribute contexts.

**[NOTE 29]** C-test/dictation/vocab scoring handled the friendly edge cases correctly: uppercase/whitespace/curly-apostrophe answers all accepted in the C-test (including the `ioner's` apostrophe gap); double-scoring is idempotent (answer spans not duplicated, verified 80→80); the vocab gate boundary behaves exactly as documented (9/32 = 28.1% valid, 10/32 = 31.25% void; f can never be exactly 0.30 with 32 pseudowords).

## (a) Findings by severity

| Severity | Count |
|---|---|
| CRITICAL | 3 |
| MAJOR | 10 |
| MINOR | 11 |
| NOTE | 5 |

## (b) Three findings I am most confident in

1. **CRITICAL 1** — README-ordered Save→Copy emits a blank tracking row (reproduced with exact byte output).
2. **CRITICAL 2** — EI/evidence answers and play-counters survive `saveSession()`, so a previous session's 100% re-scores untouched into the next session, and Play buttons go dead while showing "plays left 2" (reproduced end-to-end).
3. **MAJOR 4** — the C-test key rejects valid completions; the full 80-gap enumeration is mechanical (executed the shipped `gapText`), and "attribute", "lie", "moderate" fit the stems, the context, and the `maxlength` limits.

## (c) What I could not verify, and why

- **External citations in SOURCES.md/METHOD.md** (C-test α range, LexTALE 2022 replication, DIALANG hosting ending 2024, EF SET–TOEFL correlation, Oller's dictation claim): no attempt to fetch each paper; I verified only the speech-rate figures — B2 ≈ 118 / C1 ≈ 142 wpm do come from the cited Huang & Gráf line of work — which confirms MAJOR 8's point that they are corpus means from interview data, not cutoffs for a pruned-wpm self-timed monologue.
- **Pseudoword non-wordhood against a reference wordlist**: no dictionary on the box (`/usr/share/dict` absent); judgments in MINOR 22 are from my own lexical knowledge, not a corpus check.
- **Real TTS behaviour** (voice selection races, `cancel()`/`speak()` timing, actual rate scaling across engines): jsdom stubs speech synthesis, so MINOR 16's TTS points are code-reading plus known browser behaviour, not reproduction.
- **Absolute frequency-band accuracy of the 64 real words** beyond the internal contradiction proven in MAJOR 10: checking each against BNC/COCA ranks needs corpus data I don't have locally; the docs concede the bands are estimates, so I confined the finding to the self-contradiction, which is verifiable from the file alone.
