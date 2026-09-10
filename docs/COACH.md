# The coach's operating table — who does what, when, without being told

One page for any session (cloud Routine, ad-hoc chat, local Mac session) to know its job.
Every row is mechanical unless marked **judgement**. Nothing here changes the plan:
levers move only under `docs/TARGET.md` at time trials, and only one per cycle.

## Triggers → actions

| When | Where | What happens | Outputs |
|---|---|---|---|
| A recording lands in Drive `EnglishPractice/…` | Mac, `com.english.recording` (WatchPaths, ≤10 min) | `coach-sync.sh --on-recording`: bookshelf sync → ingest (Whisper + Azure, scripted if the transcript matches a passage) → review (checklist, ledger, drill, cards) → Anki push if open → commit + push | `logs/practice/<id>.*`, `logs/pronunciation-ledger.json`, `drills/latest.*`, `cards/queue.tsv` |
| Every night 21:40 | Mac, `com.english.nightly` | `coach-sync.sh --unattended`: pull → bookshelf (import new EPUBs, stock the phone from `logs/reading/shelf.json`) → ingest → review → **KOReader pull** (Drive mount) → **reading cards** → Anki (opened by the job if closed: push cards, sync, stats, quit) → listening → ElevenLabs → Kindle if mounted → Intervals.icu → commit + push | `logs/reading/*`, `logs/anki-stats.json`, `logs/listening/`, cards in Anki |
| Kindle plugged in | Mac, `com.english.kindle` | `coach-sync.sh --kindle-only` → the same lookup store | `logs/reading/vocab.json` |
| Daily 18:30 UTC | Cloud Routine `trig_01YRXXRq9hmK5rPfza4UVzUy` | pull → gpodder listening (if env) → finish pending harvests → Hub pull + fold → Talk-session cards → `koreader-pull` (kosync position, if env) → `reading-cards` → `reading-hub` → Hub `meta/drills`, `meta/ledger`, `meta/reading` → observations → commit + push → 5-line reply | Hub Read tab current; `cards/queue.tsv`; `observations.md` |
| Friday 18:00 UTC | Cloud Routine `trig_01Quw9v6zvapu6kkvperUVPL` | pull → Hub + diagnostic runs → weekly digest (**judgement**: patterns, 2-occurrence rule) → `weekly-rollup` → `daily-readout` → `dial` (recommend only) → Season Board → commit + push → ≤10-line reply | `observations.md`, `logs/weekly.tsv`, `progress.html` |
| Time-trial week-close (weeks 5, 10; week 12 = measurement) | Friday Routine + user | `dial.py` recommendation logged to `logs/dial-log.tsv`; **the user decides** the one lever | `logs/dial-log.tsv` |
| A new EPUB in Drive `EnglishPractice/library` | Mac (next sync) | imported; `<slug>.hub.json` written beside it; `logs/reading/books.json` registered | the book on the shelf list = on the phone |
| The user taps "Import a book…" (Read tab) | Hub page | stores `book/*` + `meta/book`, points `book_next` at B001 | the Read tab serves the book |
| Any chat with the user | Any session | harvest English passively (`observations.md` rules); never correct unsolicited | `observations.md` |

## What the coach decides on its own (harvest level, no gate)

- **Cards:** every source queues production cards (`cards/queue.tsv`); the Mac pushes them every
  night (opening Anki itself if needed), at most 25 new per rolling week across all sources (`anki-push-cards.py`). Lookups
  are carded newest-first, 5 per run (`reading-cards.py`); the Friday review may reformulate or
  retire cards (RETIRED patterns) — harvest actions, any time.
- **The shelf:** `logs/reading/shelf.json` lists what the phone holds. The coach changes it when a
  book is finished (position ≥ 97 %), when the anchor trend says the text is too hard for
  read-aloud, or when the user asks. The Mac executes at the next sync.
- **Crutch words, drill classes, passages:** from the ledger and transcripts, mechanically.
- **Flags, never scores:** low dictation, stale Anki export, zero days, no speaking — raised in the
  readout and the digests; nothing sensor-derived enters `tracking.tsv`.

## What never happens without the user

Plan levers (one per 5-week cycle, time trials only) · calendar events · Anki scheduler settings ·
new credentials or accounts · anything touching `tracking.tsv` outside a diagnostic run ·
publishing the book text anywhere public.

## Where things are

`CLAUDE.md` (rules) · `docs/PRACTICE.md` (recording loop, bookshelf) · `docs/HUB.md` (sensors,
phone and Mac setup) · `docs/TARGET.md` (season, dial) · `docs/LAUNCH.md` (the one-off checklist).
`scripts/check.sh` runs every self-test; run it before committing tooling.
