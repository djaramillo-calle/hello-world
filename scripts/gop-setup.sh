#!/usr/bin/env bash
# Build .venv-gop — the local pronunciation scorer's environment. See docs/GOP.md.
#
# DELIBERATELY SEPARATE from .venv-practice. That venv's faster-whisper/CTranslate2 pins are
# load-bearing on the Intel mac (CLAUDE.md), it has no torch, and the recording loop runs on it.
# If this environment breaks, the recording loop does not.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v espeak-ng >/dev/null 2>&1; then
  echo "espeak-ng is required (the reference text's phonemes come from it)."
  case "$(uname -s)" in
    Darwin) echo "  brew install espeak-ng" ;;
    Linux)  echo "  sudo apt-get install -y espeak-ng" ;;
  esac
  exit 3
fi

python3 -m venv .venv-gop
.venv-gop/bin/pip -q install --upgrade pip
.venv-gop/bin/pip -q install torch --index-url https://download.pytorch.org/whl/cpu
.venv-gop/bin/pip -q install transformers soundfile librosa phonemizer datasets scipy
.venv-gop/bin/python scripts/gop.py --selftest
echo "gop-setup: ready. The model (~1.2GB) downloads on first scoring run."
