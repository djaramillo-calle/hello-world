#!/usr/bin/env python3
"""Pull the two <script> blocks out of diagnostic.html so they can be
syntax-checked and unit-tested outside a browser.

    python3 scripts/extract-scripts.py && node scripts/run-tests.js
"""
import re, pathlib, sys

root = pathlib.Path(__file__).resolve().parent.parent
html = (root / "diagnostic.html").read_text()
blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
if len(blocks) != 2:
    sys.exit(f"expected 2 script blocks, found {len(blocks)}")
out = root / "scripts" / ".build"
out.mkdir(exist_ok=True)
(out / "check_bank.js").write_text(blocks[0])
(out / "check_engine.js").write_text(blocks[1])
print(f"bank {len(blocks[0])} chars, engine {len(blocks[1])} chars -> {out}")
