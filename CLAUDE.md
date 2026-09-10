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

## Anki (local sessions only)

The user's SRS lives in desktop Anki, controlled via an Anki MCP server +
AnkiConnect on their local machine. Cloud sessions cannot reach it; git is
the bridge. Conventions for any LOCAL session with the Anki MCP attached:

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

## Data hub (local sessions)

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
  `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` are set. Dual-locale by design:
  en-GB is the real score; the en-US pass exists ONLY to extract phoneme
  identities/prosody for the L1-Spanish confusion set (US reference model —
  never read it as an overall score). Uploads audio to Azure; no-retention
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
- **Morning check** ("how is my recovery?" for English): `python3
  scripts/daily-readout.py` — mechanical readout from git; add judgement,
  never a score. The Hub's readout button is the self-serve version.
- `scripts/weekly-rollup.py` now takes conversations, listening days and
  talk minutes from sensors (hub + `logs/listening/daily.json`); `--set`
  still overrides in writing. SRS days fall back to check-ins only when no
  Anki export covers the week.
- **Mac nightly job** (`scripts/install-automation.sh`, 21:40, LaunchAgent):
  `coach-sync.sh --unattended` = pull → practice ingest → Anki (AnkiConnect
  with sync when open, else `anki-revlog.py` direct read — never read the
  collection while Anki runs) → `listening-pull.py` (AntennaPod → gpodder) →
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
