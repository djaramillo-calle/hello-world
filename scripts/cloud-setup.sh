#!/bin/bash
# The cloud's practice venv (Linux x86_64, stock python3): Whisper + praat + Azure + a bundled ffmpeg.
# Idempotent; scripts/cloud-sync.py calls it when .venv-practice is missing. ~2 min on a fresh container.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "--tools" ]; then
  # markitdown for the book importer (scripts/passage-import.py looks in .venv-tools/bin) — its own venv, away from the pinned practice stack
  [ -x .venv-tools/bin/python ] || python3 -m venv .venv-tools
  .venv-tools/bin/markitdown --version >/dev/null 2>&1 || .venv-tools/bin/pip install -q 'markitdown[epub]'
  echo "tools venv OK ($(.venv-tools/bin/markitdown --version 2>/dev/null | head -1))"; exit 0
fi
if [ ! -x .venv-practice/bin/python ]; then python3 -m venv .venv-practice; fi
.venv-practice/bin/python -c "import faster_whisper, parselmouth, azure.cognitiveservices.speech, imageio_ffmpeg" 2>/dev/null || \
  .venv-practice/bin/pip install -q faster-whisper==1.2.1 ctranslate2 praat-parselmouth azure-cognitiveservices-speech imageio-ffmpeg
FF=$(.venv-practice/bin/python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")
ln -sf "$FF" .venv-practice/bin/ffmpeg
echo "cloud practice venv OK (ffmpeg → $(basename "$FF"))"
