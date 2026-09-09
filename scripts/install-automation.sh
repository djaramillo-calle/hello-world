#!/bin/bash
# Install the Mac-side automation: nightly coach-sync at 21:40 and the Kindle
# mount watcher, as user LaunchAgents. Idempotent; re-run after moving the clone.
#
#   bash scripts/install-automation.sh            # install / reinstall
#   bash scripts/install-automation.sh --remove   # uninstall both agents
#   bash scripts/install-automation.sh --run-now  # install, then fire the nightly job once
#
# Prerequisites (one-off, interactive):
#   1. git push must work without a prompt: `gh auth setup-git` (token in the macOS
#      keychain) or an SSH deploy key without passphrase in ~/.ssh/config.
#   2. Optional secrets in ~/.config/english-runbook/env (chmod 600):
#        GPODDER_USER=... GPODDER_PASS=...        (AntennaPod → gpodder.net listening)
#        INTERVALS_API_KEY=...                    (Intervals.icu custom wellness fields)
#        ELEVENLABS_API_KEY=... ELEVENLABS_AGENT_ID=...   (optional hosted voice agent)
#   3. To wake a sleeping Mac for the job: `sudo pmset repeat wakeorpoweron MTWRFSU 21:38:00`
#      (check with `pmset -g sched`). A closed lid may still not count as awake.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
UID_="$(id -u)"

remove_agent() {
  local label="$1"
  launchctl bootout "gui/$UID_/$label" >/dev/null 2>&1 || true
  rm -f "$AGENTS/$label.plist"
}

if [ "${1:-}" = "--remove" ]; then
  remove_agent com.english.nightly; remove_agent com.english.kindle; remove_agent com.english.recording
  echo "removed com.english.nightly, com.english.kindle and com.english.recording"; exit 0
fi

[ "$(uname)" = "Darwin" ] || { echo "install-automation: macOS only (launchd)"; exit 1; }
mkdir -p "$AGENTS" "$HOME/.config/english-runbook"
[ -f "$HOME/.config/english-runbook/env" ] || { touch "$HOME/.config/english-runbook/env"; chmod 600 "$HOME/.config/english-runbook/env"; }

WATCH=""
for d in "$HOME/EnglishPractice" "$HOME"/Library/CloudStorage/GoogleDrive-*/"My Drive/EnglishPractice"; do
  [ -d "$d" ] && WATCH="$WATCH    <string>$d</string>\n"
done
[ -n "$WATCH" ] || echo "warning: no EnglishPractice folder found yet (create ~/EnglishPractice or add the Drive account) — the recording watcher will have nothing to watch until you re-run this"

for label in com.english.nightly com.english.kindle com.english.recording; do
  remove_agent "$label"
  python3 - "$REPO/scripts/launchd/$label.plist" "$AGENTS/$label.plist" "$REPO" "$WATCH" <<'PY'
import sys; src, dst, repo, watch = sys.argv[1:5]
s = open(src, encoding="utf-8").read().replace("__REPO__", repo).replace("__WATCH__\n", watch.replace("\\n", "\n"))
open(dst, "w", encoding="utf-8").write(s)
PY
  plutil -lint "$AGENTS/$label.plist" >/dev/null
  launchctl bootstrap "gui/$UID_" "$AGENTS/$label.plist"
  echo "installed $label"
done
launchctl list | grep -E "com.english" || true

if [ "${1:-}" = "--run-now" ]; then
  launchctl kickstart -k "gui/$UID_/com.english.nightly"
  sleep 3; echo "--- /tmp/english-nightly.log ---"; tail -n 20 /tmp/english-nightly.log || true
fi
echo "nightly sync: 21:40 daily → /tmp/english-nightly.log · kindle: on mount → /tmp/english-kindle.log · recording: on folder change → /tmp/english-recording.log"
