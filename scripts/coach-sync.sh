#!/bin/bash
# The data hub on the Mac: run every ingest path that is currently available,
# then make one "observations: data sync" commit with whatever changed. Safe
# to run any time; each path skips gracefully when its source is absent.
#
#   scripts/coach-sync.sh               # interactive session: ingest + commit + push
#   scripts/coach-sync.sh --no-push     # ingest + commit only
#   scripts/coach-sync.sh --unattended  # nightly LaunchAgent (scripts/install-automation.sh):
#                                       #   Anki via AnkiConnect if open (sync first), else direct DB read;
#                                       #   gpodder listening pull + Intervals.icu push when keys are set;
#                                       #   pull --rebase before push; never force
#   scripts/coach-sync.sh --kindle-only # StartOnMount LaunchAgent when the Kindle is plugged in
#   scripts/coach-sync.sh --on-recording # WatchPaths LaunchAgent: a recording landed → ingest → review →
#                                       #   ledger/cards/drill → Anki (if open) → commit → push
#
# Secrets live in ~/.config/english-runbook/env (chmod 600), never in git:
#   GPODDER_USER / GPODDER_PASS [/ GPODDER_BASE]   INTERVALS_API_KEY [/ INTERVALS_ATHLETE_ID]
#   ELEVENLABS_API_KEY / ELEVENLABS_AGENT_ID       AZURE_SPEECH_KEY / AZURE_SPEECH_REGION
#   KOSYNC_USER / KOSYNC_PASS                      (KOReader progress sync — the reading position)
set -uo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-}"
mkdir -p logs cards drills   # git add below fails (exit 128, stages nothing) if any pathspec dir is absent
[ -f "$HOME/.config/english-runbook/env" ] && set -a && . "$HOME/.config/english-runbook/env" && set +a

echo "== coach-sync $(date '+%Y-%m-%d %H:%M') ${MODE} =="

if [ "$MODE" = "--unattended" ] || [ "$MODE" = "--on-recording" ]; then
  git pull --rebase --autostash --quiet origin "$(git rev-parse --abbrev-ref HEAD)" || echo "pull failed — continuing with local state"
fi
[ "$MODE" = "--on-recording" ] && sleep 45   # let Google Drive finish writing the file

if [ "$MODE" = "--on-recording" ]; then
  # 0. The recording trigger: only the practice paths, as fast as possible
  if [ -x .venv-practice/bin/python ]; then
    .venv-practice/bin/python scripts/practice-ingest.py || echo "practice ingest FAILED"
  else
    echo "practice: venv missing (run scripts/practice-setup.sh)"
  fi
  python3 scripts/practice-review.py || echo "practice review FAILED"
  python3 scripts/anki-push-cards.py || echo "anki cards FAILED"
  git add logs/ cards/ drills/
  if git diff --cached --quiet; then echo "nothing new — no commit"; else
    git commit -q -m "observations: recording reviewed (coach-sync --on-recording)" && git push -q origin HEAD && echo "committed + pushed" || echo "push failed — nightly job will retry"
  fi
  exit 0
fi

if [ "$MODE" != "--kindle-only" ]; then
  # 1. Practice recordings (local folders + any synced Drive mount)
  if [ -x .venv-practice/bin/python ]; then
    .venv-practice/bin/python scripts/practice-ingest.py || echo "practice ingest FAILED"
  else
    echo "practice: venv missing (run scripts/practice-setup.sh) — skipped"
  fi

  # 1b. Review every new recording (checklist, ledger, cards queue, drill); harvest via `claude -p` when present
  python3 scripts/practice-review.py || echo "practice review FAILED"
  python3 scripts/anki-push-cards.py || echo "anki cards FAILED"

  # 2. Anki stats: AnkiConnect when Anki is open (sync first so phone reviews are in), else the collection file directly
  if curl -s -m 2 -X POST http://127.0.0.1:8765 -d '{"action":"version","version":6}' >/dev/null 2>&1; then
    curl -s -m 60 -X POST http://127.0.0.1:8765 -d '{"action":"sync","version":6}' >/dev/null 2>&1 && sleep 5
    python3 scripts/anki-stats.py || echo "anki stats FAILED"
  elif pgrep -x Anki >/dev/null 2>&1; then
    echo "anki: running without AnkiConnect — skipped"
  else
    python3 scripts/anki-revlog.py || echo "anki: no collection readable — skipped"
  fi

  # 3. Listening (AntennaPod → gpodder-protocol server), when credentials exist
  python3 scripts/listening-pull.py || echo "listening pull FAILED"

  # 4. AI conversations from a hosted voice agent, when configured (optional upgrade path)
  python3 scripts/elevenlabs-pull.py || echo "elevenlabs pull FAILED"

  # 4b. Reading: KOReader on the phone (Autosync → Drive EnglishPractice/koreader) + kosync position
  python3 scripts/koreader-pull.py || echo "koreader pull skipped/FAILED"
fi

# 5. Kindle vocab (legacy path: needs the device plugged in over USB; writes the same logs/reading/vocab.json)
KINDLE_DB=$(ls /Volumes/*/system/vocabulary/vocab.db 2>/dev/null | head -1)
if [ -n "${KINDLE_DB:-}" ]; then
  python3 scripts/kindle-vocab.py "$KINDLE_DB" || echo "kindle sync FAILED"
else
  echo "kindle: not plugged in — skipped"
fi

# 6. Intervals.icu: today's English load next to the running data (idempotent merge)
if [ "$MODE" != "--kindle-only" ]; then
  python3 scripts/intervals-push.py || echo "intervals push FAILED"
fi

# 7. One commit for everything that changed — never force, never empty
git add logs/ cards/ drills/
if git diff --cached --quiet; then
  echo "nothing new — no commit"
else
  git commit -q -m "observations: data sync (coach-sync${MODE:+ $MODE})" && echo "committed"
  if [ "$MODE" != "--no-push" ]; then
    git push -q origin HEAD && echo "pushed" || echo "push failed — will retry next run"
  fi
fi
