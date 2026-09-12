# Independent Audit: English Signal Check (`/home/user/hello-world/diagnostic.html`)

Method: full source read; the page executed in jsdom (real DOM, real event flow) with every scoring path driven by adversarial inputs; a real Chromium (playwright) pass for layout; the author's test suite run in a sandbox copy and sabotaged to test its detection power; every C-test gap enumerated programmatically and checked against a 370k-entry wordlist; Monte Carlo simulation of the vocabulary estimator. All line numbers refer to `diagnostic.html` unless stated.

## CRITICAL

**C1. Following the README's own instructions produces a blank tracking row, and the report self-destructs on save.**
Location: `saveSession()` line 1370, `copyRow()` line 1390, `renderReport()` early return line 1266.
README step 1 says: "Hit *Save this session to history*, then *Copy result row* and append the line to `tracking.tsv`." But `saveSession()` sets `S.current = {}` (line 1382 region), and `copyRow()` reads only `S.current`. Verified: after Save-then-Copy the clipboard receives `"2026-08-29\t\t\t\t\t\t\t\t"` — a date and eight empty fields. Worse, after saving, `renderReport()` hits `if (!done.length)` (line 1266) and replaces the whole report with "Nothing measured yet" — the Copy button, the history table, and the delta table all vanish, so the user cannot even discover the correct order. The data is unrecoverable through the UI (it exists only inside `S.history`).
Fix: `copyRow` should read the last history row when `S.current` is empty; the report's early return must not swallow history/copy/delta when history exists.

**C2. The "Change since last session" table — the tool's stated core purpose — is unreachable at the moment it matters.**
Location: `renderReport()` line 1313 (`if (S.history.length >= 2) html += deltaNote();`), `deltaNote()` line 1340 (compares `history[len-2]` vs `history[len-1]` only).
Verified end-to-end: complete run 1, save; weeks later complete run 2 → open Profile → **no delta** (history has 1 entry; the current run is never compared against history). Click Save → report blanks entirely (C1). The delta comparing runs 1 and 2 first becomes visible only after you complete some module of run 3, at which point it compares two stale sessions, not the one you just did. The tool is marketed ("built to be reliable for **change**") around a table no user will ever see at the right time.
Fix: `deltaNote` should compare the current unsaved session against the last saved one, and remain visible after saving.

## MAJOR

**M1. C-test gaps have multiple correct English completions; exact-match scoring marks them wrong.**
Location: `gapText()` line 713, scoring line 781 (`val === ans` only, no alternates list).
I enumerated all 80 gaps (stems and keys) and cross-checked against a wordlist plus context. At minimum these accept a completion a competent rater would credit, but the tool rejects:
- Passage 3 `li[ve]`: "where most expensive mistakes **lie**" — at least as idiomatic as "live". "lie" fits the stem and length cap; scored wrong.
- Passage 3 `mod[est]`: "Beyond a **moderate** threshold" — "erate" is 5 chars, exactly the input's `maxlength` (n+3=5); fully grammatical; scored wrong.
- Passage 3 `comfor[table]`: "narrower and less **comforting**" — natural; scored wrong.
- Passage 2 `ear[ly]`: "arrives **earlier**, in private" — grammatical; scored wrong.
- Additionally 16 of 80 gaps are `th[e]/th[ey]/th[at]/th[em]`, where "this/that/their" are contextually defensible in several slots (e.g., "I walk to th__ station").
METHOD.md presents "Exact-match scoring" as unproblematic and cites reliability figures from properly piloted C-tests (which are piloted precisely to remove such items). Fix: an alternates list per gap, or manual-override scoring.

**M2. The "lexical reach / beyond-core" measure counts basic regular inflections as beyond-core vocabulary.**
Location: `BANK.k1` line 637 (base-form list, irregular pasts included but no regular inflections), `scoreSpeak()` line 1194-1195.
Verified: `things`, `wanted`, `working`, `friends`, `houses`, `asked`, `walked`, `goes`, `says`, `makes`, `started` are all classified **beyond-core**, while `told`, `said`, `went` are core. A beginner saying "I walked to my friends houses" scores as lexically sophisticated. Proper nouns also count (verified: Paris/Berlin/Maria → beyondRatio 31.7% = "high" flag, threshold ≥0.22 at line 1195). The measure does not measure what it claims even for tracking, because the inflection artifact scales with utterance content, not ability. Fix: lemmatize or at least strip -s/-ed/-ing before lookup; exclude capitalized non-sentence-initial tokens.

**M3. The vocabulary ±500 "noise threshold" flags pure noise as "real movement" roughly 40% of the time.**
Location: `deltaNote()` line 1348 region (`cmp("Vocabulary", ..., 500)`), METHOD.md noise table.
Monte Carlo using the tool's exact formula (8 items/band, 32 pseudowords, `(h−f)/(1−f)`, round to 100): for a stable ~5,000-family learner, SD of a single administration is ~370-400 families, so SD of a between-session difference is ~520-570. Result: **38.2% (f=.05) to 43.1% (f=.15) of no-change retest pairs exceed ±500 and get the verdict "real movement."** The claim "movement above the per-measure noise thresholds is real signal" (README, METHOD.md) is quantitatively false for this measure. The C-test's ±8 on 80 items is similarly ~1σ of a difference, not a signal threshold (partially mitigated by identical items). Fix: threshold at ~2σ (vocab ≈ ±1,100), or report intervals.

**M4. Dictation answers are revealed on scoring, inputs stay enabled, and re-scoring silently overwrites — a two-click path to a fake 100%.**
Location: `scoreDict()` line 978 — no `disabled = true` (contrast `scoreCtest` line 801), targets printed in the results table, no double-score guard.
Verified: score empty (0%, targets displayed) → paste targets into the still-active inputs → Score again → stored `pct: 1`, no flag anywhere, and this is what gets saved and tracked. The C-test also reveals all answers on scoring and permits an unflagged Clear-and-retake, but at least disables inputs. Fix: disable inputs and freeze the module's stored score after first scoring; flag re-scores.

**M5. Psychometric window-dressing: published statistics for other instruments are presented as properties of this one, and every interpretive cutoff is invented.**
Locations: overview table line 198 ("α ≈ .87–.92; parallel forms r ≈ .82" listed as *this* C-test's credentials); `ctBand()` line 815 (C-test% → CEFR cutoffs 25/40/55/68/78/86/93 — no published C-test↔CEFR equating exists for unpiloted home-made passages; passage difficulty entirely determines where these land); line 1182-1186 (wpm→CEFR notes; the B2≈118/C1≈142 corpus numbers come from a different task type and transcription protocol, and this tool computes *pruned* wpm — fillers removed at line 1150 — over a *self-typed* duration, both of which shift the number by 5-15%); line 993 ("Below 1.15× means normal conversational speed…" — the × is a multiplier on an unspecified, device-dependent TTS baseline, so 1.15× means different wpm on every machine); MTLD bands 70/45 (line 1194), filler 8% (1192), beyond-core 22%/14% (1195) — all invented, none cited. METHOD.md's "Calibration honesty" section concedes ±1 CEFR sub-level, but the UI still prints "Provisional band: **B2**" with no per-screen caveat, and the reliability figures are stated in the overview as if they were measured on this instrument. The elicited-imitation module inherits an OPI-correlation claim (line 201) from rater-scored EITs while being self-rated on a 5-point rubric by the test-taker — the validity chain it cites is severed by its own design; the caveat text ("generous by roughly the same amount every time") is an assumption, not evidence.

**M6. Nothing pins or records the TTS voice, so modules 3-4 are not "identical every run."**
Location: `speak()` line 927: `getVoices().filter(/^en/i)[0]` — takes whatever English voice happens to be first, silently falls back to the OS default when the (async-loading) voice list is empty at click time, and stores nothing about which voice was used. Browser updates, OS changes, or voice-list load timing change the stimulus. The battery's entire change-tracking argument rests on "identical items and scoring every run"; for the two audio modules that is not established, and the rate multipliers (0.95-1.40) apply to different baselines per voice. Fix: record `voice.name` in the session, warn when it changes.

**M7. The test tooling verifies almost nothing; the "verification log" is an eyeball transcript.**
Location: `scripts/run-tests.js`, `scripts/tests.js`, `logs/verification-2026-08-29.txt`, METHOD.md "Running the tests".
Verified by sabotage in a sandbox copy:
- Gutted passage 4 so it yields **3 gaps instead of 20** → suite prints `passage 4: 3 !!!` and **exits 0**. No assertion in the entire suite ever sets a non-zero exit code; `node scripts/run-tests.js` cannot fail except by crashing.
- Replaced the engine's validity gate with `const valid = true;` → suite output **identical**, still prints "f=0.31 -> VOID". Because the gate "test" in `tests.js` uses its own local reimplementation (`function sim(hitRate,f){ const valid = f<=0.30; ... }`) and never calls `scoreVocab`. It tests a copy of the idea, not the shipped code.
- The gate test's inputs f=0.29/0.30/0.31 are **unreachable**: with 32 pseudowords f is always k/32, so the real boundary is 9/32=0.281 (valid) vs 10/32=0.3125 (void). The advertised "30% ceiling" never actually adjudicates anything.
- "duplicates remaining: 0" is vacuous — it measures `BANK.k1.length - new Set(BANK.k1).size` *after* line 639 already deduplicated unconditionally (the source string contains 477 duplicate tokens).
- METHOD.md claims the suite "Checks gap counts, item-bank integrity, the validity gate, MTLD behaviour and **dictation scoring**." There is no dictation test of any kind; the MTLD "check" prints one number with no expected value.

**M8. Smart-quote apostrophes inflate the speaking metrics by ~20%.**
Location: `norm` line 967: `replace(/[^a-z0-9'\s]/g," ")` keeps straight `'` but converts `’` to a space, splitting `don’t` into `don` + `t`.
Verified: the identical transcript scores **49 words with curly apostrophes vs 41 with straight** (wpm 24.5 vs 20.5, +20%). iOS/Android keyboards and most dictation tools emit curly apostrophes; a desktop keyboard emits straight ones. Transcribe on your phone one month and your laptop the next and the "±12 wpm" delta logic reads the keyboard change as progress. Fix: normalize `’` → `'` in `norm` (as C-test scoring at line 788 already does).

**M9. Degenerate speaking inputs produce NaN on screen, a 199% self-repair rate, and unvalidated durations.**
Location: `scoreSpeak()` lines 1152-1199.
Verified: (a) 40 fillers ("um uh…") passes the ≥40-word gate, then `content.length = 0` → the visible report renders **"NaN%"** for self-repair/TTR/lexical reach; (b) one word ×300 → `repRatio = 1.987`, displayed as **"Self-repair 199%"** — the unigram loop (line 1161) and overlapping bigram loop (line 1162) double- and triple-count the same repetition, so the "ratio" is unbounded; (c) duration field: `+value || 120` (line 1153) silently substitutes 120 for 0; typing `-30` yields **wpm −200**; typing `5` (below the `min="20"` attribute, which nothing enforces) yields **wpm 1200**. Saved as-is to history. Fix: gate on content words, clamp secs to [20,600], cap repRatio at count of distinct repair sites.

**M10. Vocabulary result text is wrong at both extremes.**
Location: `scoreVocab()` lines 890-903.
Verified: (a) scoring with **nothing marked** yields "~0 word families … False-alarm rate 0% — **good discipline; the estimate is trustworthy**" with confidence "high" — an unattempted module reported as a trustworthy zero; (b) a **VOID** run (f=100%) still appends " Knowledge starts thinning at the N band…" plus a stray `</p>`, because the `firstGap` clause at line 903 is concatenated outside the `!valid` guard — the run the text says is "discarded rather than reported" leaks a band diagnosis and malformed HTML. Fix: guard both clauses on `valid`; treat 0 marks as not-attempted.

**M11. Reloading mid-session sets modules "done" while showing blank forms; one click silently destroys the stored score.**
Location: `load()` line 652 restores `S.current`; `buildAll()` rebuilds empty UIs; no input state is persisted.
Verified: score the C-test (any %), reload, tab shows done, inputs empty; click "Score this module" → stored score overwritten with **0%**, no confirmation. Fix: either persist input state, or make Score refuse/confirm when a stored result exists for the module and the form is untouched.

## MINOR

**m1. "Ceiling" logic is non-monotone.** `scoreDict` line 988 and `scoreCtest` line 803 both use `filter(≥threshold).pop()`. Verified: only sentence 10 correct → "Speed ceiling 1.40×"; only passage 4 correct (total 25%) → "ceiling C1–C2". A "highest level held" statistic must require the levels below it to hold too — and one sentence/passage per level is far too little data to call a "ceiling" at all.

**m2. C-test item construction wastes items.** Verified distribution: 44 of 80 gaps have 1-2 letter answers; 16 of 80 are th-word completions (`e`,`ey`,`at`,`em`). METHOD's "second half of every second word" is also inaccurate — the code (line 724) skips words under 3 letters entirely, a further undocumented deviation from the Klein-Braley construction whose reliability figures are being borrowed.

**m3. The item bank contradicts itself on frequency.** Verified: 7 of 8 words in the "2000" band (`careful, forest, guard, ocean, prison, silver, wonder`) are inside the tool's own "core ~1,500" list used for lexical reach. The k1 comment says "top-1000", the list is 1,546 words, the UI label says "~1,500", and the source string carries 477 duplicate tokens.

**m4. Accessibility of the tab interface and answer widgets fails basics.** Tabs (line 673-688) have `role=tab`/`aria-selected` but no `aria-controls`, no `id` linkage from panels (`role=tabpanel` with no `aria-labelledby`), and no arrow-key navigation. The vocab "know" buttons and yes/no/rubric buttons encode state only via a `data-on` color change — no `aria-pressed`, invisible to screen readers. C-test ok/bad is color-only. Computed contrast: `--ink-faint` #838C88 on ground/panel is **3.08:1 / 3.34:1** in light mode — below WCAG AA 4.5:1 — and it is used for functional text at 10-11px ("plays left 2", item numbers, unmarked "know" buttons).

**m5. Mobile: the dictation tab horizontally overflows the page.** Verified in real Chromium at 360px viewport: `scrollWidth` 481px vs 360 (`size="52"` input at line 947 renders 461px wide). The body itself scrolls sideways; C-test/vocab/overview are fine.

**m6. On a browser without speechSynthesis, plays are still consumed.** `playDict` (line 954) decrements "plays left" before `speak()` discovers there's no TTS and alerts. Verified: two clicks burn both plays with zero audio.

**m7. The filler measure only counts hesitation vocalizations.** `FILLERS` (line 1087) = um/uh/er variants only; "like", "you know", "well", "so" — the dominant English fillers — count as content words (raising wpm) and never trigger the 8% flag.

**m8. Elicited imitation bank/comment mismatch and silent sense handling.** Bank comment (line 585) says "Half the items are semantically anomalous"; actual count is **2 of 8**. Unanswered sense judgements are silently scored wrong (line 1064); the module can also be scored with nothing answered (0%, marked done).

**m9. Tracking format asymmetries.** `copyRow` matches tracking.tsv's 9 columns (verified) — but the in-page history stores no `beyond_core`, so the on-page History table can never show a column the TSV tracks; and for a degenerate transcript `pct(beyondRatio)` can emit the literal string `NaN` into the TSV.

**m10. The two-minute timer ends silently.** No sound or visual alarm at 0:00; the speaker is mid-monologue and (per the instructions) recording on a phone, so the on-screen timer must be watched continuously to be of any use. `setInterval(…,1000)` also drifts.

**m11. Unflagged score-inflation vectors in the speaking module.** Unlimited prompt redraws ("prompt shopping" against the "start within five seconds" rule), self-entered duration, and self-produced "verbatim" transcripts — none recorded or flagged. The design depends wholly on honesty here yet flags nothing (unlike the vocab module, which was built around distrust).

**m12. Dictation gives full credit for scrambled word order.** Verified: the sentence typed fully reversed scores 16/16. METHOD does document "order-insensitive token overlap", but this contradicts both the on-screen instruction ("Type exactly what you hear") and the claimed construct ("segment a fast stream into words *in real time*").

## NOTE

**n1. The "LCG" is not one.** Line 847: `seed * 1103515245` exceeds 2^53 on the first step (verified: diverges from the true modular sequence at step 0, every product loses precision). It is still deterministic across runs and platforms (IEEE-754), and the resulting shuffle is adequately mixed (longest pseudoword run: 4), so the *tracking* property holds — but the code's claim to be a specific LCG is false and its low-bit behavior is rounding artifact, not arithmetic.

**n2. MTLD is essentially correct.** Verified against an independent implementation of McCarthy & Jarvis 2010 (bidirectional, 0.72, partial-factor remainder `(1−TTR)/(1−0.72)`): agrees on normal text. Sole deviation: the code triggers a factor at TTR **≤** 0.72 where the common reading is **<**; measurable only on sequences hitting exactly 0.72 (verified: 18.47 vs 19.46 on a crafted sequence). The `<20 tokens → null` guard and `factors===0 → length` fallback are reasonable.

**n3. Pseudowords are clean but two are risky.** None of the 32 is a dictionary word (checked against 370k entries) and none is edit-distance-1 from a core word — but `zolvent` (solvent) and `prantic` (frantic) are one letter from common real words, inviting misreads under the "work fast; first instinct" instruction, each punished at high leverage through the false-alarm correction.

**n4. Gap inputs reveal the answer's exact letter count** (`size` and `maxlength` at line 755) — a hint absent from the published C-test forms whose statistics are cited, and the `maxlength = n+3` cap arbitrarily blocks longer valid alternates.

**n5. Register/spelling wrinkles.** `sceptical`, `apologised` (British) with a forced `en-US` voice; `practit[ioner's]` requires typing an apostrophe inside a gap answer (curly input is handled — verified accepted).

Verified non-findings worth recording: no XSS found — `esc()` is applied at every injection point I probed (transcript `<img onerror>`, dictation input, prompt text all rendered escaped); localStorage-blocked environments initialize and score correctly; double-clicking Score on the C-test is idempotent (no duplicate answer spans); dark-mode token coverage is complete (no hardcoded colors outside the token blocks; dark-mode contrast is better than light).

## (a) Findings by severity
- CRITICAL: 2
- MAJOR: 11
- MINOR: 12
- NOTE: 5
- Total: 30 (plus 4 explicitly verified non-findings)

## (b) Three findings I am most confident in
1. **C1** — Save-then-Copy yields a blank row and the report blanks itself: reproduced exactly, clipboard contents `"2026-08-29\t\t\t\t\t\t\t\t"`, against the README's own instructions.
2. **M2** — `things`, `wanted`, `friends`, `working` count as "beyond-core" lexical reach: reproduced directly against the shipped word list.
3. **M7** — the test suite cannot fail and doesn't test the shipped code: proved by sabotage (gutted passage → `3 !!!`, exit 0; deleted validity gate → identical output).

## (c) What I could not verify, and why
- The **exact figures in the cited literature** (C-test α .87-.92 / r .82 / .76; B2≈118 / C1≈142 wpm; the vocabulary-coverage percentages; EF SET/DET/LexTALE characterizations) against the source papers — no access to the cited PDFs from this environment. The borrowing critique (M5) does not depend on the figures being misquoted, only on their provenance; but whether they are even accurately transcribed is unconfirmed.
- **Real audible TTS behavior** — rate-multiplier audibility at 1.40×, voice quality differences across OSes — this environment has no audio; I verified the API-level logic (voice selection, play counting, cancel semantics) only.
- **Clipboard behavior on `file://` origins** (where `navigator.clipboard` may be absent — the `prompt()` fallback exists and was exercised via stub, but not in a real browser on an insecure origin).
- **The claimed ordering of evidence-inventory items "by interactional pressure"** — a subjective claim with no operationalization to test; I note only that it is asserted, not evidenced.
