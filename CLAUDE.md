# Project: Adult English — diagnosis, routine, and tracking

The user is an adult English learner (L1 Spanish, UK-based, office job
09:30–17:00 UK time, gym 18:15 most weekdays). Goal: conversational,
real-world English. Key artifacts:

- `diagnostic.html` — English Signal Check battery (form v2, post-audit).
  Re-run every 5 weeks; one row appended to `tracking.tsv` per run.
- `routine.html` — English Runbook (daily plan; focus dial, 2-conversation
  weekly floor, no work missions — removed at user request 2026-08-30).
- `docs/plan/final-plan.md` — the adjudicated plan. Its cardinal rule:
  **at most ONE plan lever changes per 5-week cycle**, and only at the
  diagnostic week-close, and only when the current dial's target metric
  missed its noise threshold.
- `docs/METHOD.md` — instrument spec, noise thresholds, form history.
- `observations.md` — the chat-based English observation log (see below).
- `docs/COACH.md` — **the operating table**: every trigger (recording, nightly,
  daily Routine, Friday, time trial, new book) → who acts → what is produced,
  plus what the coach decides alone (cards, shelf, flags) and what never
  happens without the user. Read it first in any session that is unsure
  what to do.

## Standing instruction: maintain the observation log

In every session with this user, passively note their English in their own
messages and maintain `observations.md`:

1. **Harvest, don't correct.** No unsolicited mid-chat corrections or
   rewrites of the user's sentences. Digest on request or at the weekly
   review only. Exception: if the user declares "English mode" in a chat,
   switch to prompt-style feedback (signal the breakdown, let them repair —
   never reformulate for them).
2. **Pattern discipline.** One occurrence = `WATCHING` (presumed typo).
   Two or more independent occurrences = `PATTERN` (append entry + suggest
   production-format SRS cards). No recurrence across ~4 weeks = `RETIRED`.
3. **What to watch** (from the baseline entries): article omission before
   abstract nouns; phrasal-verb avoidance / Latinate monoculture;
   subject–verb agreement; countability; collocation (also log strengths).
4. **Register honesty.** Chat is written, self-paced, technical. Never
   infer speaking ability from it, and never turn this log into a number —
   nothing from it goes into `tracking.tsv`.
5. **Adjustment gate.** Log findings may *recommend* plan changes any time,
   but plan changes are *implemented* only under the final plan's
   one-lever-per-cycle rule at a diagnostic week-close. Card and
   crutch-word-list additions are exempt (they are harvest, not levers).

A weekly Routine ("Weekly English observation review", Fridays ~18:00 UTC)
fires into the long-running session to write the digest. If working in a
fresh session, append observations with dated entries in the established
format and commit with message prefix "observations:".

## Anki

The user's SRS lives in desktop Anki (Anki MCP + AnkiConnect on the Mac) and
AnkiDroid, both synced through AnkiWeb. Two paths into it:

- **Cloud (chosen by the user 2026-09-10):** `python3 scripts/anki-cloud.py`
  — the official `anki` library's AnkiWeb sync, with `ANKIWEB_USER` /
  `ANKIWEB_PASS` as CCR environment variables (never git, never the Hub
  store, never chat). Each run: empty temp collection → full DOWNLOAD from
  AnkiWeb → queued cards added (deck, model, cap and dedupe below) → normal
  sync (incremental upload) → `logs/anki-stats.json` exported from the
  downloaded collection → queue rows marked `added`. It never full-uploads:
  if AnkiWeb asks for one it aborts and the desktop resolves it. Exit 3 when
  the variables are unset. The daily and Friday Routines run it; AnkiDroid
  and the desktop receive the cards at their next sync.
- **Mac (AnkiConnect):** `anki-push-cards.py` / `anki-stats.py` in
  `coach-sync.sh`, which opens Anki itself at night. Both paths share the
  queue (`cards/queue.tsv`) and the cap, so whichever runs first wins and the
  other finds nothing left.

Conventions for any session that adds cards (either path, or the MCP):

- Deck name: **English Runbook**. Card format: production — front = cue
  ("Say it: ...", "Complete aloud: ...", "Phrasal (instead of X): ..."),
  back = the target chunk. The user says the answer ALOUD before flipping.
- Seed deck: `seed-deck.csv` (33 cards). Import it once via MCP on first
  setup; thereafter add cards directly from `observations.md` suggestions
  and conversation harvests. Cap ~25 new cards/week; deck cap ~120 live.
- **Stats export (feeds the cloud Friday review):** when working locally,
  export a compact summary to `logs/anki-stats.json` — date, reviews done
  per day since last export, mature/young/new counts, cards with lapses
  ≥4 (leech candidates) — commit and push ("observations: anki stats").
  The weekly Routine reads this file from git; without it, the review
  evaluates chat patterns only.
- Adjustments (suspend leeches, reformulate cards, retire RETIRED-status
  patterns' cards) are harvest-level actions: allowed any time, no
  one-lever gate. Never change the scheduler settings without the user.

## Reading (KOReader on the phone; Kindle USB is the legacy path) — 2026-09-10

The reading sensor, built like the listening one: an open client that
publishes on its own, the cloud pulls. `docs/HUB.md` "Phone setup" has the
one-off steps.

- **Phone:** KOReader reads the EPUB. Its Vocabulary Builder keeps dictionary
  lookups with the sentence context; its statistics plugin keeps seconds per
  page. One two-way Autosync pair mirrors `koreader/settings/` ↔ Drive
  `EnglishPractice/koreader/`: databases up, books down. **The shelf is
  `logs/reading/shelf.json`** (committed): the coach lists the slugs the phone
  should hold; `library-sync.py` on the Mac stocks the Drive folder from
  `EnglishPractice/library/` accordingly. Progress sync (kosync,
  sync.koreader.rocks) publishes the position; the Read tab follows it.
- **Pull:** `python3 scripts/koreader-pull.py` — on the Mac (nightly and in
  `coach-sync.sh`) reads the Drive mount; anywhere with `KOSYNC_USER` /
  `KOSYNC_PASS` set (CCR environment variables + the Mac env file, never git)
  it also pulls the position; `--dir <folder>` folds sqlite files fetched by
  other means; `--check` verifies the credentials. Writes `logs/reading/`:
  `vocab.json` (unified lookup store — `kindle-vocab.py` writes the same file
  when a Kindle is plugged in), `daily.json` (minutes per day, Europe/London),
  `progress.json` (percentage → passage id), `books.json` (KOReader document
  ids = partial MD5 of the file, written by `passage-import.py`).
- **Curating the lookups (2026-09-15):** the user's own delete in KOReader's Vocabulary Builder is
  how words leave the list — he is the only one who can tell a deliberate tap from a finger-slip.
  `merge_vocab` used to ADD only, so a deletion on the phone reached nothing; a lookup that is
  absent from a full read of the database is now marked `dropped` (and `carded`, so Say-it never
  offers it) and **never erased** — the history stays and looking the word up again brings it back.
  A safety rail: if more than `PRUNE_FLOOR` of the stored koreader lookups vanish at once that is
  an emptied or reinstalled database, not an afternoon's curation, so it says so and changes
  nothing.
- **Cards:** `python3 scripts/reading-cards.py` (Mac before the Anki push;
  cloud daily) turns the newest un-carded lookups that have a usable sentence
  into production cards (front = the sentence with the word blanked, said
  aloud; back = word + sentence), 5 per run, `carded: true` once used; the
  25/week cap is enforced at the Anki push.
- **Hub:** the daily Routine runs `python3 scripts/reading-hub.py` (exit 3 =
  nothing yet) and `write_db` sets `meta/reading` from `logs/hub-reading.json`
  (gitignored, regenerated each run). The Read tab's Reading panel shows the
  position with a "Read aloud from here" button (sets `book_next`), the
  week's minutes and the recent words with their sentences.
- **Load, harvest, pointer — never a score:** `reading_min` is a load column
  in `logs/weekly.tsv` and the readout (sensor first, the Log tab's check-in
  when the sensor has nothing for that day); lookups follow the card rules
  (best usage sentences → production cards, shared 25/week cap, `carded`
  flag); the position only moves the Read tab's pointer. Nothing feeds
  `tracking.tsv`. No Amazon cookies or passwords, ever; the Kindle's
  `vocab.db` over USB remains the only Kindle route.

## Minimal Pairs (the perception drill app on the phone) — 2026-09-11

`djaramillo-calle/minimal-pairs` is its own repo and its own Android app (Kotlin, sideloaded APK
from its GitHub Releases page, built by its Actions workflow on every push). It is the HVPT drill:
one word of a pair in a random one of six British voices, tap the word heard, instant feedback,
about 40 trials in 3 minutes, half of them on words never heard before (the honest probe). Same
sensor pattern as KOReader: the app writes files into the phone folder `Documents/MinimalPairs`,
Autosync mirrors it two-way to Drive `EnglishPractice/pairs`, the cloud pulls and pushes.

- **Contract** (`docs/CONTRACT.md` in the app repo): the app writes `sessions/<id>.json`
  (immutable, per-trial rows), `state.json`, `catalog-version.txt`; the coach writes `plan.json`
  only (contrast weights 0–1, trials, untrained ratio, voices, word bands, feedback level, note).
  Contrast ids = the ledger's classes plus `long-back`, `sh/ch`, `er/or`.
- **Cloud (`cloud-sync.py`, every run):** `sync_pairs` downloads new sessions/state to the work
  dir → `python3 scripts/pairs-pull.py --dir <folder>` folds them into `logs/pairs/` (sessions
  copied once, `weekly.tsv` per ISO week and contrast, repeated misses → "Say it (pronunciation)"
  cards through the shared queue) → `plan.json` rebuilt from the ledger + recent sessions with the
  app's own `plan-from-ledger.py` (the app repo is shallow-cloned into `.cache/minimal-pairs`,
  gitignored, so both sides use one script and one catalog) → `push_plan` PATCHes Drive's
  `plan.json` when it differs. The service account cannot create files (no quota): the owner
  created `EnglishPractice/pairs/plan.json` once (2026-09-11); it is only ever updated in place.
- **Rollup:** `weekly.tsv` gains `pairs_sessions` and `pairs_untrained_pct` (percent correct on
  untrained words that week). Load + formative signal, never a score, never tracking.tsv.
- **What the app adapts alone** (`docs/ADAPTATION.md`): which contrast/pair/word/voice comes next
  and more trials for a struggling contrast, inside the plan. What only the coach changes: the
  plan. A manual override in the app is recorded as `plan_source: "override"`; talk about it,
  never silently overwrite it.
- **Reviewing it:** the Friday review reads `logs/pairs/weekly.tsv` and `state.json`; a contrast
  whose untrained accuracy stays under ~80% for two weeks gets more weight, one above ~95% for
  two weeks less; `untrained_shortfall` growing means widen `band` (plan-from-ledger does it).
  The perception line is a candidate third line on the Season Board (with the anchor read and
  the daily pages) once the diagnostic is retired.

## Say it (the production half of the pronunciation loop) — 2026-09-13

The reads flag words; `scripts/sayit.py` turns the repeat offenders into something he can practise and
be scored on, inside the Minimal Pairs app. The loop: read aloud → Azure flags words → sayit picks the
words he actually misses → he says the sentence in the app → the cloud scores that recording → the word
retires or goes to the tutor.

- **Two sources, one drill** (`source` on every word; added 2026-09-15 at the user's request):
  `flagged` — words the reads caught him mispronouncing, a motor habit to break; and `new` —
  words he looked up while READING, which he has never said at all. His argument for the second,
  and it is right: an Anki card he reads silently teaches the meaning and never tells him whether
  the mouth was right, and a brand-new word has no model to correct, so hearing one and being
  scored is the whole intervention. `source` is an additive field — the app shows both without a
  change, so it works on the build already on the phone. **Reading lookups no longer become Anki
  cards** (`reading-cards.py`, `LOOKUPS_GO_TO_SAYIT`): the same lookup must not cost him two daily
  obligations, and `carded` stays the shared "already spent" flag, now set by `sayit.py`. Cards
  queued before that date still go up as the cap allows. A `new` word that is still active after
  `TUTOR_WEEKS` goes to `parked`, never to `tutor`: not knowing a rare word is not a motor problem
  for a human to hear. New words already on the list SURVIVE a rebuild — the claim would otherwise
  spend a lookup that was never served.
- **Selection needs the frequency list** (`.cache/minimal-pairs/data/sources`, the app repo's
  clone): `library/` is gitignored, so in a cloud container the passage text is usually missing,
  `read_on` collapses and the miss rate becomes meaningless — on 2026-09-15 "under" scored 4 flags
  in 1 read (rate 4.0) and seven of ten offered words were function words. So the rate is clamped
  at 1.0, a word inside the commonest `TOO_COMMON` needs `COMMON_MIN_READS` actually-counted
  occurrences before its rate is believed, and rarity breaks the ties. For `new` words the lists
  are a SOFT signal only — used as a gate they threw away *conglomeration*, *erudition*,
  *lamentation* and *conflagration* to catch four bits of OCR damage — so an unrecognised word is
  merely ranked last. Hard rejects there (`worth_saying`): shape (non-alpha, under three letters,
  no vowel), a capital inside the sentence (*Volga*, *Comintern*, *Stalin* are names), and anything
  inside the commonest `TOO_COMMON_NEW` (2,000). **THE MACHINE SCREENS FINGER-SLIPS; THE USER
  CURATES.** The threshold was raised to 15,000 on 2026-09-15 and put back the same day: asked
  which lookups were mistakes, he named function words only — "and, that, in, under, all, its,
  come, which, only, our, situation" — and said he *meant* *hatred*, *haste*, *spectacle*,
  *medieval*, *swift*, *glimpse*, *comrades*, *sheer*, *midst*. No threshold can separate a tap he
  meant from one he did not, so it only removes what a finger-slip looks like, and the judgement is
  his: **he deletes the word in KOReader's Vocabulary Builder**, and `koreader-pull` marks it
  `dropped` (see below). `worth_saying` also runs over the words ALREADY on the list, so a change
  to the screen clears what it now rejects instead of leaving it standing.
- **Several sentences per word, rotated by day** (`carriers`, `todays`; 2026-09-15, the user's idea).
  Repeating one sentence is blocked practice: it improves the rehearsed sentence and does not carry.
  Varying the carrier is the **contextual-interference effect** — worse during practice, better at
  retention and *transfer* — and transfer is exactly what his data says is missing (98–99 on the
  sentence he had just heard, the same words flagged inside 15–84 minutes of reading). The sentences
  come from `library/<slug>.json` `chunks[].text`, **never invented**: a word with only one usable
  sentence in the books keeps it. `sentences: [{text, clip}]` is additive and `sentence`/`clip` stay
  the live pair, so the build already on the phone works unchanged; an app build could pick per
  attempt instead. Rotation is by DAY, not by run — cloud-sync runs several times a day and the
  sentence must not change under him mid-session. `looks_clean` rejects the scan's debris (a
  footnote number welded to a word, "1J", stray single capitals): a human skims past them, a neural
  voice reads them aloud and then scores him against a reference nobody would say.
- **The unit is the word IN ITS SENTENCE, never alone.** His failures are connected-speech failures
  (unstressed syllables collapsing, final consonants dropping) and an isolated word is a different motor
  task. The sentence is one he actually read, taken from the passage the review named — never invented.
- **Selection is a RATE, not a count** (`MIN_RATE`): flagged / times actually read. A count alone promotes
  function words — "the" flagged 3× across 200 occurrences is noise, "imperialist" flagged 3× out of 4 is
  broken. `read_on` undercounts when a passage's text is not in `library/` locally, which biases rates
  upward uniformly; the ranking still holds.
- **Scoring is INSTANT, on the phone, with the learner's OWN separate Azure resource** (free tier, its
  own key, a different region from the coach's — Azure allows one F0 per subscription per region). Decided
  2026-09-14 after the cloud-only design was tried: a sync runs a few times a day, so cloud-only scoring
  means no feedback whenever the coach is not running, and the coach becomes a single point of failure for
  a daily habit. The coach's own key still never reaches the phone. The app writes one immutable
  `sayit/scores/<ts>_<id>.json` per attempt; `sayit.py --score` takes that score as-is and only calls Azure
  itself when the phone could not (no key, no network, an error) — the fallback, never the rule.
- **ONE coach→app file, `sayit.zip`** (words.json + results.json + clips/<id>.ogg, en-GB neural TTS).
  The Drive service account has no storage quota and can only PATCH files that already exist, so the owner
  created an empty `sayit.zip` once (2026-09-13, alongside `plan.json` 2026-09-11) and `push_file` in
  cloud-sync overwrites it in place forever. Never try to create a Drive file from the service account.
- **Status:** `active` → `retired` after 2 attempts at accuracy ≥ 80 → `tutor` when still active after 3
  weeks (a motor problem a human should hear, not more self-practice). `logs/sayit/results.json` is the
  history; formative only, nothing reaches `tracking.tsv`.
- Every `cloud-sync.py` run: score the new attempts → rebuild the words → push the zip. The app contract
  lives in `docs/CONTRACT.md` of the app repo and must not drift from `scripts/sayit.py`.

## The cloud does the sync (since 2026-09-10) — the Mac is optional

`python3 scripts/cloud-sync.py` is the coach's sync from any fresh container:
`scripts/drive.py` (Google Drive with a service account — `GDRIVE_SA_JSON_B64`
as a CCR environment variable, the key file base64 on one line; the account is
shared on `EnglishPractice` and on `com.nll.asr`, the recorder's upload root)
→ bookshelf (`library-sync`, passage files mirrored to Drive, the phone folder
stocked Drive-side from `logs/reading/shelf.json`) → new recordings downloaded
by Drive id + md5 (`logs/practice/.drive.json`) → `practice-ingest` in
`.venv-practice` (`scripts/cloud-setup.sh` builds it, Whisper + Azure) →
`practice-review` → KOReader databases when changed (`logs/reading/.drive.json`)
→ `koreader-pull` → `reading-cards` → `anki-cloud` → `reading-hub` → commit +
push. Two Routines run it: morning 07:30 UTC (the 06:45 page scored before
work) and the daily 18:30 UTC review. Nothing large ever passes through a chat
context: the Drive connector is for listing, `drive.py` for bytes.

## Data hub (local sessions, optional)

`scripts/coach-sync.sh` is the single entry point for all data ingestion:
practice recordings + Anki stats (when Anki is open) + KOReader reading data
(from the Drive mount) + Kindle vocab (when plugged in), one "observations:
data sync" commit. Run it at the START of
every local session and before Friday reviews; each path skips gracefully
when its source is absent.

## Practice feedback loop (local sessions)

Recorded speaking practice flows to the coach automatically. Built 2026-08-30
from an adversarially-verified tool investigation (workflow, 12 agents).

- **Capture:** any audio in `~/EnglishPractice/`, or in an `EnglishPractice`
  folder under any Google Drive desktop mount (`~/Library/CloudStorage/
  GoogleDrive-*/My Drive/EnglishPractice`), is ingested wholesale; files
  named `eng*` in the Voice Memos iCloud folder or iCloud Drive
  `EnglishPractice/` are too. All sources activate automatically once they
  exist (the Apple sources are vestigial — the user's phone is an Android
  Poco F7 Pro; phone recordings arrive via the Drive folder). Naming convention for typing: "eng 432", "eng ai", "eng warmup",
  "eng debrief". The user's chosen upload target is the Drive folder
  `EnglishPractice` (id `1oPS4iDVAY4MD8oZBQvX0zIarTwQbvEnQ`) in the
  udea.isabella2028@gmail.com account — the account the session's Google
  Drive connector reaches, so cloud sessions can LIST it for unprocessed
  recordings (metadata only; avoid pulling audio via connector except as a
  one-off — base64 through context is expensive). Local ingestion of that
  folder requires the account added to the Google Drive desktop app.
- **Ingest:** `.venv-practice/bin/python scripts/practice-ingest.py --commit`
  (venv from `scripts/practice-setup.sh`; the Python 3.13 + pinned-wheel
  choices are load-bearing on this Intel mac — never bump pins without
  re-verifying x86_64 wheels exist). Output per recording in
  `logs/practice/`: whisper transcript with per-word confidence, wpm/fillers,
  de Jong & Wempe pause/rate metrics, pitch stats, low-confidence
  pronunciation suspects. Idempotent (content-hash state file).
- **Azure pronunciation assessment** (`scripts/azure_pa.py`) activates when
  `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` are set. **ONE en-US pass since
  2026-09-16**, carrying the score, the IPA phonemes and prosody together.
  It was two passes (en-GB score + en-US phonemes), which billed every
  recording twice and blew the 5-audio-hour/month free tier on 2026-09-14;
  the fix collapsed them into one, but into en-GB, and that was wrong.
  **Microsoft's own docs: prosody "is only available in the `en-US` locale",
  the IPA alphabet is en-US only, and "only `en-US` provides phoneme name
  alongside scores. Other locales receive phoneme scores without names."**
  The en-GB single pass returned 550 EMPTY phoneme symbols, so the confusion
  classes silently fell back to spelling guesses, and it returned a prosody
  number for a locale that does not support the feature. The user chose en-US
  outright on 2026-09-16: he lives in the UK now and may not later, and the
  09-14 objection (non-rhotic r, the BATH/TRAP split) never applied to an
  L1-Spanish speaker who is rhotic and has neither.
  **MEASURED on the same audio, transcript and reference** (five reads
  rescored): prosody 52–59 → 81–86, fluency +3, accuracy and completeness
  within a point or two, and the shape of the series held. Named phonemes
  went from 0 to 70/70 and the class counts roughly tripled (i/ii 15→50,
  s/z 8→44, schwa 7→32). **en-GB and en-US rows are DIFFERENT SERIES** —
  every ledger read row carries `locale`; never draw one line through both.
  The 09-14 read is still en-GB (the quota ran out mid-rescore); re-run it
  with `scripts/rescore-reads.py --only 2026-09-14` once the quota resets.
  **Also true since 2026-09-15:** asking for prosody makes Azure fold it into
  `PronScore`, so `pron` is a different composite before and after that date.
  **`accuracy`, `fluency` and `completeness` are per-dimension** — but they
  too shift with the locale, so read them within a locale, not across it.
  **The F0 tier is 5 audio hours a month and 2026-09 is spent** (the rescores
  cost ~3h on top of the ingests): until it resets or the resource moves to
  S0, recordings transcribe (Whisper is local) but come back unscored with
  `CancellationReason.Error 1007, Quota exceeded`. The wait for continuous
  recognition scales with the audio and a run that does not finish RAISES —
  a fixed 600s ceiling once made an 84-minute read look like a successful
  assessment of nothing, and the empty result was written over good scores.
  Uploads audio to Azure; no-retention
  terms verified 2026-08. Verified 2026-09-09 on the F0 free tier from the
  cloud (`scripts/azure-check.py`, report in `logs/azure-check.json`):
  scripted assessment, completeness, IPA phonemes and prosody all work.
  The key also lives as `AZURE_SPEECH_KEY`/`AZURE_SPEECH_REGION` environment
  variables of the Default Cloud Environment; the Mac still needs them in
  its env file for the recording loop.
- **Feedback rules:** telemetry is FORMATIVE only — nothing feeds
  tracking.tsv. Patterns in practice transcripts follow the observation-log
  discipline (2+ occurrences → PATTERN, production cards, shared 25/wk cap).
  ASR suspicion is a screen, not a verdict — have the tutor confirm the top
  suspects monthly. Session-start coach check: read new `logs/practice/`
  files; the Friday review digests the week.

## Season (the sport frame) — added 2026-09-09 audit

- `docs/TARGET.md` — the race and the 12-week season: baseline (week 0),
  time trials weeks 5/10/12, road race in week 12 (30-min conversation with
  a stranger, comprehensibility ≤3/9), targets = baseline + one noise
  threshold per domain with absolute floors. Read it before any plan talk.
- `scripts/dial.py` — mechanical dial recommendation (profile → dial,
  noise thresholds, held/moved/abandoned). Run at every time-trial
  week-close; log to `logs/dial-log.tsv`; overrides go in the `reason`
  column. PRE-SEASON until tracking.tsv has a row. Levers change only at
  time trials ≥ 4 weeks apart (weeks 5 and 10); the week-12 row is a
  MEASUREMENT. DECODE is never set mechanically (low dictation is a flag;
  the authentic-audio check decides, by override).
- `scripts/weekly-rollup.py` — Friday training log → `logs/weekly.tsv`
  (SRS days/reviews from Anki stats, recordings + wpm/filler from
  logs/practice, dial, floor check). Self-report via
  `--set conversations=N human_conversations=N listening_days=N notes="..."`
  (a total without the human split leaves floor_ok "partial"). Load ≠ ability.
- `scripts/build-progress.py` → `progress.html` — the Season Board (pace
  chart). Rebuild after every diagnostic and every Friday review; publish
  the wrapper-stripped copy to the existing artifact URL:
  https://claude.ai/code/artifact/43e3b4e1-75f6-45d4-b1e5-ba4b04a0c1ef
- **Stages** (`logs/stage.json`, `docs/COACH.md`): 1 = SRS + one recorded
  page a day (floors: recorded pages 5, SRS days 5); 2 adds one AI
  conversation + listening; 3 = the full runbook. Stage 1 since 2026-09-10
  at the user's request. The readout, the weekly rollup and the Hub's Today
  tab follow the stage; promotion is proposed by the Friday review and
  confirmed by the user in chat. Not a lever.
- `scripts/check.sh` — one command: jsdom suite + all Python self-tests.
  Run before committing tooling changes.
- Friday Routine (trig_01Quw9v6zvapu6kkvperUVPL) now: pull → digest →
  rollup → dial → rebuild board → republish → push → short reply asking for
  the two self-report numbers.
- Calendar events for the four fixed sessions remain user-gated (never
  created without explicit confirmation).

## The Hub (sensor layer) — added 2026-09-09

Intervals.icu is the user's hub for running/gym/anthropometry; `docs/HUB.md`
is the same architecture for English. Read it before touching ingestion.

- `hub.html` → artifact https://claude.ai/code/artifact/81ce98f7-d1a4-4904-b268-84245e8fabe9
  (capabilities `db` + `sample`; republish the stripped copy at that URL,
  never as a new artifact — the database belongs to the URL). Tabs: Talk (AI
  voice conversation under the standing brief; transcript + telemetry +
  harvest → `sessions/<id>`), Log (one-tap check-ins → `days/<date>`), Today
  (prescription, floors, morning readout), Week. `meta/config` holds dial,
  topic, crutch words, baseline date.
- **Pulling the Hub from the cloud** (any session, and the Friday Routine):
  Artifact `read_db` on collections `days` and `sessions` with `out_dir`,
  then `python3 scripts/hub-fold.py <dump>` → `logs/hub/`. The diagnostic
  artifact (823a99e1…) now stores each saved run in its own DB, collection
  `runs` (field `tsv` is the tracking row) — pull it before appending to
  `tracking.tsv`; the paste path still works.
- **Hub writes need a version (2026-09-12, resolved 2026-09-13):** the artifact runtime
  rejects `write_db` set/update/delete on an EXISTING document unless the call carries
  `if_version` (read the doc first, resend with the version `read_db` returned). Older
  Artifact tools have no such parameter and simply cannot refresh `meta/*`; container
  2.1.270 has it. **So the Hub writes belong in the same FRESH session that runs
  `cloud-sync.py`**, not in the long-running coach session, whose container may be older.
  If a session cannot write: say so in the reply rather than reporting the Hub refreshed,
  and leave the documents alone — never delete and recreate them to get around it (delete
  needs the version too, and the page's history belongs to the URL). git stays the source
  of truth meanwhile.
- **Morning check** ("how is my recovery?" for English): `python3
  scripts/daily-readout.py` — mechanical readout from git; add judgement,
  never a score. The Hub's readout button is the self-serve version.
- `scripts/weekly-rollup.py` now takes conversations, listening days and
  talk minutes from sensors (hub + `logs/listening/daily.json`); `--set`
  still overrides in writing. SRS days fall back to check-ins only when no
  Anki export covers the week.
- **Mac nightly job** (`scripts/install-automation.sh`, 21:40, LaunchAgent):
  `coach-sync.sh --unattended` = pull → practice ingest → Anki (the job opens
  Anki itself when closed: push cards, sync, stats, quit; `anki-revlog.py`
  direct read only if it cannot start — never read the collection while Anki
  runs) → `listening-pull.py` (AntennaPod → gpodder) →
  optional `elevenlabs-pull.py` → `koreader-pull.py` → Kindle if mounted → `intervals-push.py`
  (custom wellness fields `Eng*`, idempotent merge) → one commit, push,
  never force. Secrets in `~/.config/english-runbook/env`, never in git.
- **gpodder from the cloud:** `scripts/listening-pull.py` runs here too when
  `GPODDER_USER` / `GPODDER_PASS` are set as environment variables of this
  CCR environment (claude.ai environment settings — the only persistent,
  private place the cloud has; storing them in git or in an artifact store
  is refused). If set, every Routine runs the pull and commits
  `logs/listening/`; if not, the Mac's nightly job is the only listening
  sensor. Credentials never go into git, the Hub store, or chat.
- Sensor data is load or harvest: `logs/hub`, `logs/listening`,
  `logs/ai-sessions`, Intervals.icu fields never feed `tracking.tsv`.
  Transcripts feed `observations.md` under the 2-occurrence rule.

## The recording loop — added 2026-09-09

A recording landing in the `EnglishPractice/Recordings` Drive folder (any
subfolder of `EnglishPractice` is scanned; the watcher lists each subfolder) is the trigger;
everything after it is automated (`docs/PRACTICE.md`). Read that file before
touching `practice-*.py`, the ledger, the cards queue or the passages.

- Kinds from the filename: `eng read <id>` (read-aloud, scored SCRIPTED
  against `passages/passages.json`; `A00` is the weekly anchor, Mondays),
  `eng ai`, `eng 432`, `eng debrief`, `eng drill`, else `free`.
- Mac: `com.english.recording` LaunchAgent (WatchPaths on the folder) →
  `coach-sync.sh --on-recording` → `practice-ingest.py` (Whisper + Azure PA,
  scripted for reads) → `practice-review.py` (checklist per kind → `.review.json/.md`,
  `logs/pronunciation-ledger.json`, `cards/queue.tsv`, `drills/latest.*`;
  harvest via `claude -p`, else left `pending`) → `anki-push-cards.py`
  (AnkiConnect, 25/week cap, dedupe by front) → commit + push.
- Cloud (daily Routine 18:30 UTC + Friday): finish pending harvests from the
  transcripts, queue cards from Hub Talk harvests, then `write_db` on the Hub:
  `meta/drills` ← `drills/latest.json`, `meta/ledger` ← `logs/pronunciation-ledger.json`
  (the Read tab shows the drill and the anchor trend). `meta/passages` ← `passages/passages.json`
  whenever the passages change.
- The checklist: fluency for every kind; pronunciation = scripted Azure for
  reads (confusion classes th, b/v, i/ii, j/y, s/z, -ed, schwa, s-cluster, h,
  cat/cut), unscripted screen otherwise; grammar/vocabulary harvest only for
  conversation kinds (a read-aloud's grammar is the text's). Words flagged on
  2+ recordings become "Say it (pronunciation)" cards. Stage 1 = reading
  daily; stage 2 adds recorded conversations once reading holds ~3 weeks.
- Never a score: the anchor series is formative; nothing feeds tracking.tsv.
  The daily read-aloud entered the plan in pre-season (no lever spent).
- **The book / bookshelf** (2026-09-10): the Drive folder
  `EnglishPractice/library/` holds the EPUBs (`Author__Title.epub`) and the
  processed files. `scripts/library-sync.py` (Mac, nightly + before each
  ingest) imports new books via `scripts/passage-import.py` →
  `library/<slug>.json` (gitignored — copyrighted; mirrored to Drive) +
  `<slug>.hub.json` in Drive, which the Hub's Read tab imports itself
  ("Import a book…" → `book/*`, `meta/book`; text never crosses a cloud
  session). The Read tab serves passages in order via `meta/config.book_next`;
  the ingest's passage detection reads `library/`. Current book: Arendt, The
  Origins of Totalitarianism, 1433 passages (already in the Hub).

## Repo conventions

- Branch: `claude/adult-language-learning-gnk7i1`. Commit and push after
  meaningful changes; no PRs unless asked.
- `diagnostic.html` and `routine.html` are standalone pages (full head).
  Their published artifacts are wrapper-stripped copies — republish via the
  existing artifact URLs, never as new artifacts.
- Tests: `node scripts/test.js` (jsdom; non-zero exit on failure). Run
  before committing any change to `diagnostic.html`. Changing items,
  scoring keys, wordlists, or thresholds is COMPARABILITY-BREAKING: bump
  the form version in `docs/METHOD.md` and warn the user that tracking
  history resets.
