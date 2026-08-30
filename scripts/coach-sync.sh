#!/bin/bash
# The data hub: run every ingest path that is currently available, then make
# one "observations: data sync" commit with whatever changed. Safe to run any
# time; each path skips gracefully when its source is absent.
#
#   scripts/coach-sync.sh            # ingest + commit + push
#   scripts/coach-sync.sh --no-push  # ingest + commit only
set -uo pipefail
cd "$(dirname "$0")/.."

echo "== coach-sync $(date '+%Y-%m-%d %H:%M') =="

# 1. Practice recordings (local folders + any synced Drive mount)
if [ -x .venv-practice/bin/python ]; then
  .venv-practice/bin/python scripts/practice-ingest.py || echo "practice ingest FAILED"
else
  echo "practice: venv missing (run scripts/practice-setup.sh) — skipped"
fi

# 2. Anki stats (needs desktop Anki open)
if curl -s -m 2 -X POST http://127.0.0.1:8765 -d '{"action":"version","version":6}' >/dev/null 2>&1; then
  python3 scripts/anki-stats.py || echo "anki stats FAILED"
else
  echo "anki: not running — skipped (open Desktop/Anki.app to include SRS stats)"
fi

# 3. Kindle vocab (needs the device plugged in over USB)
KINDLE_DB=$(ls /Volumes/*/system/vocabulary/vocab.db 2>/dev/null | head -1)
if [ -n "${KINDLE_DB:-}" ]; then
  python3 scripts/kindle-vocab.py "$KINDLE_DB" || echo "kindle sync FAILED"
else
  echo "kindle: not plugged in — skipped"
fi

# 4. One commit for everything that changed
if git status --porcelain logs/ | grep -q .; then
  git add logs/
  git commit -m "observations: data sync (coach-sync)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
  if [ "${1:-}" != "--no-push" ]; then git push && echo "committed + pushed"; else echo "committed (not pushed)"; fi
else
  echo "nothing new — no commit"
fi
