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
echo "Usage: .venv-practice/bin/python scripts/practice-ingest.py [--commit]"
