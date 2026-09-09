# The recording loop — read, record, and the rest happens by itself

The unit of training is a recording. It lands in the `EnglishPractice/Recordings`
Drive folder from the phone (any subfolder of `EnglishPractice` is scanned); from that moment nothing needs a hand. This
file is the evaluation framework and the pipeline that runs it.

## Why recordings, and why reading first

Adherence is the binding constraint of the whole program. A read-aloud is the
cheapest speaking act there is: open the Hub, read for three minutes, stop.
The file is the check-in. Reading also gives the one signal that needs a
known text to be accurate: pronunciation scored against a reference.
Conversation recordings come second, once the habit holds; they carry the
grammar and vocabulary signal instead.

| Stage | Recording | Daily cost | What it measures | Trigger |
|---|---|---|---|---|
| **1 · Read** (now) | `eng read <id>` — 3′, one passage a day; Mondays the **anchor** `A00` | 3 min | pronunciation (scripted), fluency, the anchor trend | file lands → pipeline |
| **2 · Talk** (when stage 1 holds 3 weeks) | `eng ai` (a recorded AI conversation), `eng 432` (Friday), `eng debrief` | 12–20 min | grammar, vocabulary, fluency; pronunciation as a screen | same |
| any time | `eng drill` — the ledger's minimal pairs | 2 min | the confusion classes | same |

## The checklist, per kind

Every recording is scored on **fluency**. The rest depends on what the
recording can honestly tell us.

**Fluency (all kinds)** — words per minute (fillers removed), filler share,
syllables per second and articulation rate, pause count and mean pause
(de Jong & Wempe), pitch median and range. Trend, not target.

**Pronunciation** —
- *Read-aloud*: Azure Pronunciation Assessment in **scripted mode**, en-GB
  reference: accuracy, fluency, completeness, per-word errors
  (mispronunciation, omission, insertion); the en-US pass adds phoneme
  identities so each flagged word maps to a **confusion class** for a
  Spanish speaker: `th`, `b/v`, `i/ii`, `j/y`, `s/z`, `-ed`, `schwa`,
  `s-cluster`, `h`, `cat/cut`. The anchor passage's scores are kept as a
  series: the pronunciation time trial, weekly.
- *Conversation*: unscripted assessment (rougher) and Whisper low-confidence
  words as a screen. Never a verdict; the tutor confirms the top suspects
  monthly.
- Without an Azure key: Whisper confidence only, and the report says so.

**Grammar and vocabulary (conversation kinds only)** — the transcript is
harvested under the observation-log discipline: article omission, phrasal-
verb avoidance, agreement, countability, tense, collocation. Two independent
occurrences make a pattern; a pattern makes a production card. Vocabulary
worth keeping (chunks used well or nearly) becomes cards too. A read-aloud is
never harvested for grammar: the text supplied it.

**Output of every review** — `logs/practice/<id>.review.json` and a readable
`.review.md`; the **ledger** `logs/pronunciation-ledger.json` (class tallies,
word tallies, anchor history); new rows in `cards/queue.tsv`; and
`drills/latest.md` regenerated from the ledger's top three classes (minimal
pairs plus passage lines that contain your own flagged words).

## The pipeline (what runs where)

```
phone recorder ──auto-upload──▶ Drive: EnglishPractice
                                        │ Google Drive desktop mount
Mac LaunchAgent com.english.recording (WatchPaths) ──▶ coach-sync.sh --on-recording
   practice-ingest.py   Whisper transcript · fluency · Azure PA (scripted for reads)
   practice-review.py   checklist · ledger · cards queue · drill · harvest via `claude -p`
   anki-push-cards.py   queued cards → Anki deck (if Anki is open; else the 21:40 job)
   git commit + push
cloud (this session, daily Routine 18:30 UTC + Friday review)
   finishes any harvest left pending, folds hub sessions, refreshes the Hub's drill and trend,
   keeps the observation log; the Friday review reads the week's ledger and card queue
```

The harvest backend on the Mac is the Claude Code CLI you already have
(`claude -p`, logged in; no API key). It runs with **no tools** and the
transcript goes in as fenced data on stdin: whatever was said (or played)
near the microphone is judged, never obeyed. The reply is not trusted
wholesale either — counts are capped (6 errors, 4 vocabulary, 4 cards),
strings are cleaned and length-capped, and every card front is forced into
the production cue format before it reaches the queue. If the CLI is
unavailable the review is written with the harvest marked pending and the
cloud coach completes it the same day. A file that cannot be ingested (empty,
half-synced, not audio) is quarantined by content hash and skipped, so it
never blocks newer recordings. Cards reach Anki through AnkiConnect with the 25-new-cards-per-week
cap, deduplicated by front; `cards/queue.tsv` is the audit trail.

## Phone setup (one-off)

1. A recorder app that saves to a fixed folder, with a filename you can type
   at save time. Names: `eng read A00`, `eng read R03`, `eng ai`, `eng 432`,
   `eng debrief`, `eng drill`. Case and separators do not matter.
2. **Autosync for Google Drive** (MetaCtrl): one folder pair from that folder
   to `My Drive/EnglishPractice/Recordings` in the udea account, upload-only, instant
   sync on Wi-Fi and mobile. Free tier caps files at 10 MB — fine for reads
   (3 min ≈ 2–3 MB); the Pro upgrade is needed for 20-minute conversations.
   Easy Voice Recorder Pro's built-in Drive upload is the alternative.
3. Hub → Read shows today's passage, the exact filename, and the drill.

## Mac setup (one-off, after `docs/HUB.md`)

`bash scripts/install-automation.sh` installs the recording watcher alongside
the nightly job. It watches `~/EnglishPractice` and every
`GoogleDrive-*/My Drive/EnglishPractice` mount, plus their immediate subfolders
(`Recordings`), as they exist at install time;
re-run it after adding the Drive account. Set `AZURE_SPEECH_KEY` and
`AZURE_SPEECH_REGION` in `~/.config/english-runbook/env` to turn on the
pronunciation assessment. First run: check that scripted assessment returns
`completeness` on the F0 tier and whether prosody needs the paid tier.

## Rules

Load and harvest, never ability: nothing here feeds `tracking.tsv`. The
anchor series is formative and comparable only across the same voice, mic
and text. Cards obey the weekly cap; patterns obey the two-occurrence rule;
plan levers obey the one-per-cycle rule. The daily read-aloud was added in
pre-season and belongs to the plan as a whole.
