# Hub launch — the actions to a first working version

Everything is built; nothing has run end to end yet. This is the ordered list
to a first working version: sensors reporting, one recording reviewed by
itself, cards in the deck, the season clock started. Tick the live copy at
the Hub Launch Checklist artifact (ticks persist); this file is the record.

Owner: **you** (one-off, ~90 minutes in total, split across a phone sitting
and one Mac session), **me** (in chat or by the daily/Friday Routines), or
**auto** (runs by itself once the step above it is done).

## A · Phone (~35 min)

| # | Action | Verify | Owner |
|---|---|---|---|
| A1 | Open the Hub link on the Poco (Chrome), add it to the home screen. Open Read: today's passage shows. | Read tab shows a passage and a filename | you |
| A2 | Hub → Log → Season settings: tutor day. Save. (Baseline date comes at C4.) | "saved" | you |
| A3 | Install **AntennaPod**; create a gpodder.net account (or note if registration is closed → tell me, we self-host oPodSync); Settings → Synchronization → log in, device `poco`. Subscribe the 2–3 shows of the week's topic. | one episode played ≥1 min shows in the gpodder web UI | you |
| A4 | Recorder app saving to a fixed folder + **Autosync for Google Drive** folder pair → `My Drive/EnglishPractice` in the udea account, upload-only, instant. | a test file `eng read A00` appears in the Drive folder within a minute | you |
| A5 | Tap "Read out this morning" once and, on Tuesday, "Start a 20-minute AI conversation": allow Claude and the microphone when asked. | a readout renders; a Talk session ends with a harvest | you |

## B · Mac, one local session (~40 min)

| # | Action | Verify | Owner |
|---|---|---|---|
| B1 | `git pull`. If `.venv-practice` is missing: `bash scripts/practice-setup.sh` (Python 3.13 pins are load-bearing). | `.venv-practice/bin/python -c "import faster_whisper"` prints nothing | you |
| B2 | Google Drive desktop: add the udea account so `~/Library/CloudStorage/GoogleDrive-udea…/My Drive/EnglishPractice` exists. | folder visible in Finder | you |
| B3 | Secrets in `~/.config/english-runbook/env` (chmod 600): `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION=uksouth` (free F0 Speech resource in the Azure portal), `GPODDER_USER` / `GPODDER_PASS`, `INTERVALS_API_KEY` (Intervals → Settings → Developer). Optional: `ELEVENLABS_*`. | file exists, not in git | you |
| B4 | Make `git push` prompt-free: `gh auth setup-git` (or an SSH deploy key without passphrase). | `git push` from a terminal asks nothing | you |
| B5 | `bash scripts/install-automation.sh` — installs the nightly job, the Kindle watcher and the recording watcher (re-run after B2 so the Drive path is watched). | prints the three `installed …` lines | you |
| B6 | Dry run by hand: `bash scripts/coach-sync.sh --unattended`. | log shows practice/anki/listening/intervals lines, one commit, "pushed" | you |
| B7 | **First recording end to end:** record `eng read A00` on the phone (A4). Watch `/tmp/english-recording.log`. | `logs/practice/<date>-eng-read-a00.review.md` appears in git with scripted Azure scores incl. `completeness`; if `prosody` is missing, note it (paid tier) | you → me |
| B8 | Leave Anki open one evening across 21:40. | queued cards appear in the English Runbook deck; `logs/anki-stats.json` re-exported | you |
| B9 | Intervals.icu → wellness page: add the `Eng*` fields to the fitness chart. | fields visible after the first push | you |

## C · Coach and season (~15 min of yours, the rest automatic)

| # | Action | Verify | Owner |
|---|---|---|---|
| C1 | Daily Routine (18:30 UTC) finishes pending harvests, folds Hub sessions, refreshes the Read tab's drill and trend. | its 5-line reply; Read tab shows a drill after B7 | auto |
| C2 | Friday review (Sep 11, 18:00 UTC) rolls the week from sensors. | weekly log row with sensor-filled columns | auto |
| C3 | Calendar events: say "go" and I create the seven proposed events, nothing else touched. | events on the udea calendar | you → me |
| C4 | **Baseline:** Sun Sep 13, 09:30, rested, `diagnostic.html`, all six modules, "Save this session". Then Hub → Log → Season settings → baseline date. | run stored in the diagnostic's DB; I append the tracking row; Hub strip reads WEEK 1 from Mon Sep 14 | you → me |
| C5 | First anchor time trial: Mon Sep 14, 06:45, `eng read A00`. | anchor trend shows its first row | you → auto |

## D · Reading material (when you have the file)

| # | Action | Verify | Owner |
|---|---|---|---|
| D1 | Put the book as a DRM-free EPUB/PDF in `~/EnglishLibrary/` on the Mac (never in git: `library/` is ignored — copyrighted text stays local and in the private Hub store). | file present | you |
| D2 | I build `passage-import.py` (markitdown → 150-word chunks → Hub Read tab in order) and the transcript-to-text alignment. | Read tab serves the next unread chunk; reviews list misread words | me |

## On hold (deliberately)

Drill tab (minimal-pair identification with several voices, then production
with a recogniser check) and Listen tab (sentence decoding at speed from the
passages). Ship after the read-aloud has held two weeks.

## Order that matters

A4 before B7. B2 before B5. B3 before B6. C4 before anything is "in season".
Everything else can happen in any order.
