#!/bin/bash
# One command to verify the whole system. Non-zero exit on any failure.
set -e
cd "$(dirname "$0")/.."
echo "== diagnostic page (jsdom suite) =="; node scripts/test.js | tail -2
echo "== python tooling =="
for s in dial weekly-rollup build-progress hub-fold listening-pull anki-revlog intervals-push daily-readout elevenlabs-pull practice-review anki-push-cards; do
  python3 "scripts/$s.py" --selftest
done
for f in scripts/*.py; do python3 -m py_compile "$f"; done
bash -n scripts/coach-sync.sh; bash -n scripts/install-automation.sh
for p in scripts/launchd/*.plist; do python3 -c "import plistlib,sys; plistlib.load(open(sys.argv[1],'rb'))" "$p"; done
python3 -c "import json; P=json.load(open('passages/passages.json')); assert P['anchor']['id']=='A00' and len(P['passages'])>=8; print('passages.json ok')"
echo "== hub page =="
node -e "const fs=require('fs');const m=fs.readFileSync('hub.html','utf8').match(/<script>([\s\S]*?)<\/script>/);new Function(m[1]);console.log('hub.html script parses')"
echo "== all checks passed =="
