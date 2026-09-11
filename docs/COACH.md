# The coach's operating table — who does what, when, without being told

One page for any session (cloud Routine, ad-hoc chat, local Mac session) to know its job.
Every row is mechanical unless marked **judgement**. Nothing here changes the plan:
levers move only under `docs/TARGET.md` at time trials, and only one per cycle.

## Triggers → actions

| When | Where | What happens | Outputs |
|---|---|---|---|
| Morning 07:30 UTC and evening 18:30 UTC | Cloud Routines (`cloud-sync.py`, via the Drive service account) | pull → bookshelf (Drive `EnglishPractice/library`: import new EPUBs, passage files back to Drive, phone folder stocked from `logs/reading/shelf.json`) → **new recordings** downloaded from `EnglishPractice/Recordings` and `com.nll.asr/EnglishPractice` → ingest (Whisper + Azure, scripted when the transcript matches a passage) → review (checklist, ledger, drill, cards) → KOReader databases (when changed) → **Minimal Pairs** sessions + state (Drive `EnglishPractice/pairs`, folded by `pairs-pull.py`; repeated misses → cards; `plan.json` rebuilt from the ledger and PATCHed back to Drive) → reading cards → Anki (AnkiWeb) → reading document → commit + push. The morning run is what puts the 06:45 page's score on the Hub before work. | `logs/practice/<id>.*`, `logs/pronunciation-ledger.json`, `drills/latest.*`, `cards/queue.tsv`, `logs/reading/*`, `logs/anki-stats.json` |
| (Optional, legacy) a Mac with the Drive desktop mount | `coach-sync.sh` LaunchAgents | the same steps locally, within 10 minutes of a recording, plus Kindle over USB and Intervals.icu. Not required since 2026-09-10: the cloud does it all. | same files |
| Daily 18:30 UTC | Cloud Routine `trig_01YRXXRq9hmK5rPfza4UVzUy` | **`cloud-sync`** (above) → gpodder listening (if env) → finish pending harvests → Hub pull + fold → Talk-session cards → Hub `meta/drills`, `meta/ledger`, `meta/reading` → observations → commit + push → 5-line reply | cards on AnkiWeb (AnkiDroid/desktop at next sync); `logs/anki-stats.json`; Hub Read tab current; `observations.md` |
| Friday 18:00 UTC | Cloud Routine `trig_01Quw9v6zvapu6kkvperUVPL` | pull → Hub + diagnostic runs → weekly digest (**judgement**: patterns, 2-occurrence rule) → `weekly-rollup` → `daily-readout` → `dial` (recommend only) → Season Board → commit + push → ≤10-line reply | `observations.md`, `logs/weekly.tsv`, `progress.html` |
| Time-trial week-close (weeks 5, 10; week 12 = measurement) | Friday Routine + user | `dial.py` recommendation logged to `logs/dial-log.tsv`; **the user decides** the one lever | `logs/dial-log.tsv` |
| A Minimal Pairs session completed on the phone | next cloud sync (Autosync carries the file) | `logs/pairs/sessions/<id>.json` copied once; `logs/pairs/weekly.tsv` (untrained-word accuracy per contrast and week); words missed on 2+ sessions → "Say it (pronunciation)" cards; `logs/pairs/plan.json` rebuilt (ledger counts + recent misses) and pushed to the phone | the app's next session follows the new plan; the Friday review reads the weekly table |
| A new EPUB in Drive `EnglishPractice/library` | next cloud sync | imported; `<slug>.hub.json` written beside it; `logs/reading/books.json` registered | the book on the shelf list = on the phone |
| The user taps "Import a book…" (Read tab) | Hub page | stores `book/*` + `meta/book`, points `book_next` at B001 | the Read tab serves the book |
| Any chat with the user | Any session | harvest English passively (`observations.md` rules); never correct unsolicited | `observations.md` |

## Stages (adherence first) — `logs/stage.json`, mirrored to the Hub's `meta/config.stage`

| Stage | The day | Floors per week | Promotion rule |
|---|---|---|---|
| **1** (from 2026-09-10) | 06:45: SRS aloud on the phone, then one page read aloud, recorded. Nothing else is prescribed. Mondays the page is the anchor. | recorded pages ≥ 5 · SRS days ≥ 5 | reading held ≥ 5 days/week for 3 consecutive weeks → the Friday review proposes stage 2 |
| **2** | + one AI conversation (Tuesday, Hub → Talk, 20′) + narrow listening 15′ on 3 days; the pronunciation drill appears before the page when the ledger flags a class on 2+ recordings | + conversations ≥ 1 · listening days ≥ 3 | 3 weeks with the AI conversation kept → stage 3 |
| **3** | the full runbook (`routine.html`): tutor Thursday, 4/3/2 Friday, dial slot Wednesday | conversations ≥ 2 (≥ 1 human) · SRS 5 · listening 5 · recordings ≥ 1 | — |

A stage change is not a plan lever (pre-season staging is in the plan); the user confirms it in
chat ("stage 2") and the coach flips `logs/stage.json` + `meta/config.stage`. The miss rule at
every stage: one missed day costs nothing; two in a row is the only red line, and the readout says so.

## What the coach decides on its own (harvest level, no gate)

- **Cards:** every source queues production cards (`cards/queue.tsv`); the cloud pushes them to
  AnkiWeb daily (`anki-cloud.py`, when the credentials are in the environment) and the Mac pushes
  whatever is left at night (opening Anki itself if needed), at most 25 new per rolling week across all sources (`anki-push-cards.py`). Lookups
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
new credentials or accounts (AnkiWeb's were the user's own decision, 2026-09-10) · anything touching `tracking.tsv` outside a diagnostic run ·
publishing the book text anywhere public.

## Where things are

`CLAUDE.md` (rules) · `docs/PRACTICE.md` (recording loop, bookshelf) · `docs/HUB.md` (sensors,
phone and Mac setup) · `docs/TARGET.md` (season, dial) · `docs/LAUNCH.md` (the one-off checklist).
`scripts/check.sh` runs every self-test; run it before committing tooling.
