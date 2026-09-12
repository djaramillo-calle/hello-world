# Sensor investigation — automated data ingestion for the English program

**Date:** 2026-09-09. **Question:** Intervals.icu gives the running/gym/
anthropometry program a hub: every activity flows in from a different app and
a model evaluates it daily. What is the equivalent for the language program —
which activities can be *sensed* automatically, by which tools, and what
remains self-report?

Four parallel investigations (web-verified where the sandbox could reach the
sources; anything marked *unverified* was only seen in search snippets).
Verdicts feed `docs/HUB.md`.

## Verdict table — one row per activity

| Activity | Sensor | Fidelity | Cost | Path into git | Verdict |
|---|---|---|---|---|---|
| AI voice conversation | **English Hub → Talk** (this repo's page: browser speech recognition + Claude via the `sample` capability + speech synthesis; transcript, turn telemetry and an end-of-session error harvest stored in the artifact database) | Text is browser-normalised: word counts, turns, repair prompts reliable; fillers not; speech-time estimated | free | Artifact `read_db` → `scripts/hub-fold.py` | **Primary now** |
| AI voice conversation (upgrade) | ElevenLabs Agents (public web widget; real ASR with per-turn offsets; agent-side "learner_errors" data collection; `GET /v1/convai/conversations`) | High | Starter ≈ $5/mo ≈ 75 min, then $0.08/min (pricing page *unverified*) | `scripts/elevenlabs-pull.py` (cron) | Optional upgrade when the free path proves limiting |
| AI voice apps (ChatGPT voice, Claude app voice, Gemini Live, Praktika, Speak, TalkPal, ELSA, Gliglish, Langua, Loora…) | none | — | — | account data export only, days of latency | **Dead end** for automation. Langua is the best *manual* option (transcript + feedback PDF) |
| Tutor session | italki iCal feed (attendance) + Classroom local recording with consent → `practice-ingest.py`; or Preply Lesson Insights (transcript + audio download, manual) | Medium | — | Calendar connector (attendance) + Drive folder (audio) | Attendance automatable; content stays half-manual: paste the tutor's correction list into Hub → Log |
| Recorded speaking (4/3/2, debriefs) | Android recorder with auto-upload to the `EnglishPractice` Drive folder (Easy Voice Recorder Pro ≈ £5, or Autosync folder pair) → Drive desktop mount → `practice-ingest.py` (Whisper, de Jong & Wempe metrics) | High | ≈ £5 one-off | nightly LaunchAgent | **Already built**; now scheduled |
| Attended listening | **AntennaPod → gpodder.net** (free) or self-hosted oPodSync; AntennaPod uploads a `play` action on every pause with `started`/`position` seconds; `GET /api/2/episodes/{user}.json?since=` | High (true played seconds, timestamped) | free | `scripts/listening-pull.py` (nightly, or from the cloud) | **Primary.** Requires moving podcast listening to AntennaPod |
| Listening via Spotify / YouTube / Pocket Casts / Podcast Addict | Spotify recently-played excludes episodes; YouTube watch history API removed 2016; Pocket Casts unofficial API needs the password and has no play dates; Podcast Addict backup has `playback_date` only | — | — | — | **Dead ends** |
| Android per-app usage (Digital Wellbeing / Tasker / Automate) | foreground time only; podcast audio plays with the screen off | wrong metric | — | — | Rejected |
| SRS reviews | Desktop Anki: AnkiConnect when open (sync first); **direct SQLite read of `collection.anki2` when closed** (exclusive lock while open makes a live read unsafe) | Exact (reviews, seconds, retention, leeches) | free | `scripts/anki-revlog.py` / `anki-stats.py` via nightly LaunchAgent | **Primary.** Phone reviews reach the Mac only after a desktop sync — the nightly job triggers one when Anki is open |
| SRS from the phone directly | AnkiDroid content provider exposes cards/decks, no review log; Tasker can only fire a sync intent | — | — | — | Not possible; route via AnkiWeb → desktop |
| Reading (Kindle) | `vocab.db` over USB, now triggered automatically by a `StartOnMount` LaunchAgent | Lookups only | free | `scripts/kindle-vocab.py` | Automated on plug-in. Reading time has no API (Amazon data export takes weeks). Readwise = highlights only, optional |
| Time trials (Signal Check) | `diagnostic.html` now also writes each saved run to its artifact database (`runs/<date>`) | Exact | free | Artifact `read_db` → `tracking.tsv` | Paste step removed |
| Everything else (reading minutes, personal-circle conversations, tutor self-repair y/n) | **Hub → Log** one-tap check-in | Self-report | free | `hub-fold.py` | Residual self-report, one screen, ~20 seconds |

## The hub itself — where the data lives and who evaluates it

Two candidates were checked against Intervals.icu's role for running:

1. **Intervals.icu as the single hub.** Verified: custom wellness fields
   (`CustomItem` of type `INPUT_FIELD`, created once via
   `POST /athlete/{id}/custom-item`) are written as top-level keys in
   `PUT /athlete/{id}/wellness/{date}` (a merge, so idempotent), charted on
   the fitness page, and returned by the same `GET /wellness` the running
   model already reads. They never touch CTL/ATL. Non-sport use is inside the
   terms. Outbound webhooks exist only for approved OAuth apps, so the
   direction is push-from-git, not pull-by-Intervals. **Verdict: yes for the
   daily mirror** — `scripts/intervals-push.py` pushes `EngListenMin`,
   `EngSrsReviews`, `EngConversations`, `EngTalkMin`, `EngRecordings`,
   `EngWpm`, `EngFillerPct`, so the morning "how is my recovery" check sees
   the language load in the same call.
2. **Git + the artifact database as the system of record.** The repo already
   holds every log; the Hub page adds a live store the cloud coach can read
   and write without a local machine. **Verdict: this stays the record**;
   Intervals.icu is a mirror for the morning check.

## Evaluation cadence (the "morning recovery" equivalent)

- **Daily, mechanical:** `scripts/daily-readout.py` — season position,
  yesterday, week-to-date load vs floors, streak flags (two zero days; two
  days without speaking; second week under the conversation floor; stale Anki
  export; leeches), today's prescription. The Hub's "Read out this morning"
  button does the same from the live store with Claude's judgement on top.
- **Weekly, adaptive:** the Friday Routine, now pulling the Hub database
  before the rollup.
- **Every 5 weeks, structural:** the time trial and the one-lever dial.

## Not verified live (watch the first run)

- gpodder.net registration currently open (the service had 500s in March 2026;
  oPodSync is the self-hosted fallback with the same API).
- ElevenLabs conversation endpoints and pricing against a real account.
- Intervals.icu `select`-type custom field shape (only numeric fields are
  created by the script, deliberately).
- Whether `osascript quit` of Anki takes the sync-on-close path.

## Sources

Intervals.icu: API spec https://intervals.icu/api/v1/docs · custom wellness
fields https://forum.intervals.icu/t/custom-wellness-fields/23188 · webhooks
https://forum.intervals.icu/t/webhooks-develpment/125147 · terms
https://forum.intervals.icu/t/intervals-icu-api-terms-and-conditions/114087.
Listening: AntennaPod sync source (PlaybackService, SynchronizationQueueImpl,
GpodnetService on GitHub) · gpodder API https://github.com/gpodder/mygpo/blob/master/doc/api/reference/events.rst
· oPodSync https://github.com/kd2org/opodsync · Spotify recently-played docs ·
YouTube Data API revision history. Conversation: ElevenLabs widget/webhook docs
(github.com/elevenlabs/skills, elevenlabs-python types), Vapi docs
(github.com/VapiAI/docs), Chromium issue 40324711 (continuous recognition on
Android), italki/Preply help pages (snippets), UCU recording-consent guidance.
SRS/reading: Anki `rslib/src/storage/sqlite.rs` (exclusive locking), Anki
manual (files, syncing, sync-server), AnkiDroid API wiki, sqlite.org WAL docs,
launchd.plist(5), pmset(1), Readwise Kindle import docs.
