# The Hub — sensors, ingestion and the daily evaluation loop

The running program has Intervals.icu: watch, gym app and scale push into one
place and a model reads it every morning. This is the same architecture for
English. Two stores, one loop.

```
 PHONE                         MAC (nightly 21:40, LaunchAgent)          CLOUD (Claude session / Routine)
 ─────                         ────────────────────────────────          ────────────────────────────────
 AntennaPod ──play actions──▶ gpodder.net ◀── listening-pull.py          Artifact DB (English Hub)
 recorder ──"eng *.m4a"────▶ Drive folder ──▶ practice-ingest.py           ▲  Talk sessions, check-ins
 AnkiDroid ──sync──▶ AnkiWeb ──▶ desktop Anki ──▶ anki-stats / anki-revlog   │  diagnostic runs
 KOReader ──Autosync──▶ Drive koreader/ ──▶ koreader-pull.py ──▶ git ──▶ reading-hub.py ──▶ meta/reading
         ──kosync──▶ sync.koreader.rocks ◀── koreader-pull.py (position, from the cloud too)
 Kindle (USB, legacy) ──StartOnMount──────────▶ kindle-vocab.py (same vocab store)
                                              intervals-push.py ──▶ Intervals.icu (EngListenMin…)
                                              git commit + push ──▶ GIT ◀── read_db + hub-fold.py
                                                                            daily-readout.py / weekly-rollup.py / dial.py
                                                                            Season Board · Friday digest · morning readout
```

## The English Hub page

`hub.html` → published at https://claude.ai/code/artifact/81ce98f7-d1a4-4904-b268-84245e8fabe9
with the `db` and `sample` capabilities (republish the wrapper-stripped copy
at that URL; never as a new artifact — the database belongs to the URL).

| Tab | What it senses | Where it writes |
|---|---|---|
| **Talk** | The Tuesday AI conversation: push-to-talk or hands-free speech recognition (en-GB), Claude as the partner under the standing brief (no reformulation; "Sorry, what do you mean?" on breakdowns; three repeated errors every ten turns; pushback), reply read aloud. Counts learner turns, words, estimated speaking seconds, repair prompts. "End & harvest" asks Claude for ≤6 errors, repeated patterns, self-repair y/n, and 3 production cards. | `sessions/<id>` (full transcript + telemetry + harvest); `days/<date>.conversations.ai` and `talk_min` bumped |
| **Log** | 20-second check-in: listening minutes, SRS done, reading, tutor/circle/work conversations, tutor self-repair y/n + correction list, recording done, note. Season settings: baseline date, tutor day. | `days/<date>`; `meta/config` |
| **Today** | Season strip (week, days to the next time trial), today's prescribed slots at real clock times (dial-aware Wednesday), week-to-date floors as tiles, yesterday, and the **morning readout** button (Claude, four lines, formative). | reads only |
| **Week** | 28-day load table, learner-words-per-session chart, session list with harvested errors. | reads only |

Speech recognition on Android Chrome runs one utterance at a time (continuous
mode has been broken there for years), so the page restarts recognition per
turn; hands-free mode plays the system chime between turns. Text is
browser-normalised: word counts and turn lengths are reliable, filler counts
are not — those come from recordings.

The diagnostic (`diagnostic.html`) also writes every saved run to *its own*
artifact database as `runs/<date>` (same items, same scoring; form v2
unchanged).

## Reading the Hub from the cloud

```
Artifact read_db  url=<hub>  db_op=list  collection=days      out_dir=<dump>
Artifact read_db  url=<hub>  db_op=list  collection=sessions  out_dir=<dump>
python3 scripts/hub-fold.py <dump>          # → logs/hub/days.json, sessions.json, transcripts/
Artifact read_db  url=<diagnostic> db_op=list collection=runs  # → append tsv field to tracking.tsv
```

Then `python3 scripts/daily-readout.py` for the morning check, or the Friday
sequence (`weekly-rollup.py` → `dial.py` → `build-progress.py`). The rollup
takes conversations, listening days and talk minutes from the sensors; a
`--set` still overrides them, in writing.

## Mac automation (one-off setup, ~10 minutes)

1. `bash scripts/install-automation.sh` — installs three LaunchAgents:
   `com.english.nightly` (21:40, `coach-sync.sh --unattended`),
   `com.english.kindle` (on mount, Kindle-only sync) and
   `com.english.recording` (on a change in the EnglishPractice folders; skipped
   until such a folder exists — re-run after adding the Drive account). Logs in
   `/tmp/english-nightly.log`, `/tmp/english-kindle.log`, `/tmp/english-recording.log`.
2. Make `git push` prompt-free: `gh auth setup-git` (token in the keychain)
   or an SSH deploy key without passphrase.
3. Secrets in `~/.config/english-runbook/env` (chmod 600, never in git):
   `GPODDER_USER`, `GPODDER_PASS`, `INTERVALS_API_KEY`, optionally
   `ELEVENLABS_API_KEY` + `ELEVENLABS_AGENT_ID`, `AZURE_SPEECH_*`.
4. Optional: `sudo pmset repeat wakeorpoweron MTWRFSU 21:38:00` so a sleeping
   Mac wakes for the job. A closed lid may still not count.
5. Leave desktop Anki open in the evening when possible: the job then syncs
   first (pulling the phone's reviews) and reads through AnkiConnect. When
   Anki is closed it reads `collection.anki2` directly — safe, but blind to
   phone reviews until the next desktop sync.

What the nightly job does, in order: `git pull --rebase` → practice ingest
from the Drive mount → Anki (sync + AnkiConnect, or direct read) → listening
pull → optional ElevenLabs pull → KOReader pull (Drive mount + kosync) → Kindle if
mounted → Intervals.icu push → one
commit, one push, never force, never empty.

## Phone setup (one-off, ~15 minutes)

- **AntennaPod** (free): Settings → Synchronization → gpodder.net, log in,
  device name `poco`. Move all English podcast listening here. YouTube and
  Spotify cannot report listening; they stay off the log unless checked in.
- **Recorder with auto-upload** into the `EnglishPractice` Drive folder
  (Easy Voice Recorder Pro, or Autosync for Google Drive with a folder pair).
  Names: "eng 432", "eng ai", "eng warmup", "eng debrief".
- **KOReader** (free, F-Droid or GitHub APK) — the reading sensor:
  1. Copy the EPUB to the phone (Drive → download, or USB) and open it in
     KOReader. Long-press a word → dictionary → "Add to vocabulary builder";
     or turn on Settings → Vocabulary builder → "Auto add new words".
  2. Progress sync: top menu → ⚙ → Progress sync → register a username and
     password on the default server, enable "Auto sync". Put the same two
     values as `KOSYNC_USER` / `KOSYNC_PASS` in the cloud environment
     variables and in `~/.config/english-runbook/env` on the Mac.
  3. **Autosync for Google Drive** (free tier, one folder pair): phone folder
     `koreader/settings` (internal storage) → Drive folder
     `EnglishPractice/koreader`, upload-only. That folder holds
     `vocabulary_builder.sqlite3` and `statistics.sqlite3`; the Mac's nightly
     job reads them from the Drive mount.
  Reading aloud: record with the recorder while reading from KOReader; the
  ingest finds the passage from the transcript, no name needed.
- **English Hub** on the home screen (Chrome → Add to Home screen). The first
  Talk or readout asks once to allow Claude; the first Talk asks for the
  microphone.
- Optional: **Intervals.icu** wellness page — the seven `Eng*` fields appear
  after the first push; add them to the fitness chart.

## What is still self-report

Personal-circle and work conversations, whether the tutor pushed you to
self-repair, and the tutor's correction list (reading minutes come from
KOReader; the Log tab's chip only covers days the phone did not sync). All of it is one
screen in Hub → Log, and the Friday review asks for nothing else.

## Rules that do not change

Load is adherence, never ability: nothing in `logs/hub`, `logs/listening`,
`logs/reading`, `logs/ai-sessions` or Intervals.icu feeds `tracking.tsv`. Transcripts are
harvest for the observation log under the 2-occurrence rule. One lever per
5-week cycle; sensors change what the coach *knows*, not what it may *change*.
