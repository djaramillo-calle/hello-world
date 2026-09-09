#!/usr/bin/env python3
"""Render a LaunchAgent template: __REPO__ → the repo path, __WATCH__ → one <string> per watched folder.
Values are XML-escaped (a path with & < > must still produce a valid plist).

    python3 scripts/launchd/render.py <template.plist> <out.plist> <repo> [watch dir ...]
    python3 scripts/launchd/render.py --selftest
"""
import plistlib, sys, tempfile, pathlib
from xml.sax.saxutils import escape

def render(template: str, repo: str, watch) -> str:
    lines = "".join(f"    <string>{escape(str(d))}</string>\n" for d in watch)
    return template.replace("__REPO__", escape(repo)).replace("__WATCH__\n", lines).replace("__WATCH__", lines)

def render_file(src, dst, repo, watch):
    out = render(pathlib.Path(src).read_text(encoding="utf-8"), repo, watch)
    plistlib.loads(out.encode("utf-8"))          # must parse before it is written
    pathlib.Path(dst).write_text(out, encoding="utf-8")
    return out

def selftest():
    here = pathlib.Path(__file__).resolve().parent
    repo = "/Users/x/R&D <new>/hello-world"
    watch = ["/Users/x/Library/CloudStorage/GoogleDrive-a&b@gmail.com/My Drive/EnglishPractice",
             "/Users/x/Library/CloudStorage/GoogleDrive-a&b@gmail.com/My Drive/EnglishPractice/Recordings"]
    with tempfile.TemporaryDirectory() as td:
        for t in sorted(here.glob("*.plist")):
            out = render_file(t, pathlib.Path(td) / t.name, repo, watch)
            d = plistlib.loads(out.encode())
            assert "__REPO__" not in out and "__WATCH__" not in out, t.name
            assert any(repo in str(v) for v in d.get("ProgramArguments", [])) or repo in str(d), t.name
            if "__WATCH__" in t.read_text(): assert d["WatchPaths"] == watch, d["WatchPaths"]
    print("launchd/render.py selftest: OK")

if __name__ == "__main__":
    if "--selftest" in sys.argv: selftest(); sys.exit(0)
    src, dst, repo, *watch = sys.argv[1:]
    render_file(src, dst, repo, watch)
