#!/bin/bash
# One command to verify the whole system. Non-zero exit on any failure.
set -e
cd "$(dirname "$0")/.."
echo "== diagnostic page (jsdom suite) =="; node scripts/test.js | tail -2
echo "== python tooling =="
python3 scripts/dial.py --selftest
python3 scripts/weekly-rollup.py --selftest
python3 scripts/build-progress.py --selftest
for f in scripts/*.py; do python3 -m py_compile "$f"; done
bash -n scripts/coach-sync.sh
echo "== all checks passed =="
