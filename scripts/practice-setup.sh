#!/bin/bash
# One-time setup for the practice feedback loop (see CLAUDE.md).
#
# PLATFORM WARNING: this repo's owner runs a 2020 Intel MacBook Pro. The pins
# below are load-bearing — Python MUST be 3.13 (onnxruntime shipped its last
# macOS x86_64 wheel for cp313; the stock homebrew python3 is 3.14 and cannot
# run faster-whisper), and the x86_64 wheel supply for this stack is
# end-of-life-adjacent, so never bump these without re-verifying wheels exist.
set -euo pipefail
cd "$(dirname "$0")/.."

PY313="${PY313:-/Users/dj14/.homebrew/bin/python3.13}"
"$PY313" -m venv .venv-practice
.venv-practice/bin/pip install \
  faster-whisper==1.2.1 \
  ctranslate2==4.8.1 \
  onnxruntime==1.23.2 \
  praat-parselmouth==0.4.7 \
  azure-cognitiveservices-speech==1.51.2
.venv-practice/bin/python -c "import faster_whisper, parselmouth, azure.cognitiveservices.speech; print('practice venv OK')"
# Book import (scripts/passage-import.py via library-sync.py) needs markitdown; it gets its own venv so its
# dependency tree can never disturb the pinned practice stack above.
"$PY313" -m venv .venv-tools && .venv-tools/bin/pip install -q 'markitdown[epub]' \
  && .venv-tools/bin/markitdown --version >/dev/null && echo "tools venv OK (markitdown)" \
  || echo "markitdown install failed — book import will need it (bash scripts/practice-setup.sh again later)"
echo "Usage: .venv-practice/bin/python scripts/practice-ingest.py [--commit]"
