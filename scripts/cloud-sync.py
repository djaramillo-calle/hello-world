#!/usr/bin/env python3
"""The cloud's coach-sync: everything the Mac's nightly job did, from a fresh container, via Drive.

    python3 scripts/cloud-sync.py [--no-push] [--skip-audio] [--dry-run]
    python3 scripts/cloud-sync.py --selftest

Needs GDRIVE_SA_JSON_B64 (scripts/drive.py). In order:
  1. bookshelf: EPUBs in Drive EnglishPractice/library and EnglishPractice/koreader → imported when no
     passage file exists (markitdown, ~1.5 min; passages are rebuilt each run — a service account cannot
     store files in a personal Drive), Hub documents for new books left in library/hub/<slug>/ for the
     Routine to write_db; the phone folder is what the user drops there (shelf removals best effort)
  2. recordings: every new audio file under EnglishPractice/Recordings and com.nll.asr/EnglishPractice
     (by Drive file id + md5, logs/practice/.drive.json) → downloaded → practice-ingest (Whisper + Azure,
     scripted when the transcript matches a passage) → practice-review (ledger, drill, cards)
  3. reading: EnglishPractice/koreader/*.sqlite3 (when changed) → koreader-pull → reading-cards
  4. anki-cloud (queue → AnkiWeb, stats ← AnkiWeb, when its credentials exist) → reading-hub
  5. one commit "observations: cloud sync", push (never force)
Every step skips cleanly when its source is absent; nothing here is a score, nothing feeds tracking.tsv.
"""
import hashlib, importlib.util, json, os, pathlib, shutil, subprocess, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
LIB = REPO / "library"
PRACTICE = REPO / "logs" / "practice"
DRIVE_STATE = PRACTICE / ".drive.json"
READING_STATE = REPO / "logs" / "reading" / ".drive.json"
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".opus", ".flac", ".mp4", ".webm", ".3gp", ".amr", ".wma", ".caf"}
BOOK_EXT = {".epub", ".txt", ".md"}
RECORDING_ROOTS = ["EnglishPractice/Recordings", "com.nll.asr/EnglishPractice"]

_MODULES = {}
def _load(name):
    """One instance per sibling script (so a selftest's patches on it hold across calls)."""
    if name not in _MODULES:
        spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / f"{name}.py")
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); _MODULES[name] = m
    return _MODULES[name]

def load_json(p, default):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError): return default

def dump_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

class Drive:
    """Thin adapter over scripts/drive.py so the selftest can swap in a folder-backed fake."""
    def __init__(self, key): self.d = _load("drive"); self.key = key
    def resolve(self, path): return self.d.resolve(self.key, path)
    def children(self, folder_id): return self.d.list_children(self.key, folder_id)
    def walk(self, folder_id): return list(self.d.walk(self.key, folder_id))
    def download(self, file_id, dest): return self.d.download(self.key, file_id, dest)
    def upload(self, path, folder_id, name=None): return self.d.upload(self.key, path, folder_id, name)
    def copy(self, file_id, folder_id, name=None): return self.d.copy(self.key, file_id, folder_id, name)
    def trash(self, file_id): return self.d.trash(self.key, file_id)

def run(cmd, **kw):
    print("$", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], **kw).returncode

def sync_library(drv, work, log=print, dry=False):
    """Drive library → local (JSON + EPUBs without JSON) → library-sync → new files back to Drive; then the phone folder."""
    lib_folder = drv.resolve("EnglishPractice/library")
    if not lib_folder: log("library: Drive folder missing — skipped"); return {}
    entries = {f["name"]: f for f in drv.children(lib_folder["id"]) if f["mimeType"] != "application/vnd.google-apps.folder"}
    kf = drv.resolve("EnglishPractice/koreader")
    if kf:   # a book dropped straight into the phone folder is imported too (its passages then live in the run's library/)
        for f in drv.children(kf["id"]):
            if pathlib.Path(f["name"]).suffix.lower() in BOOK_EXT and f["name"] not in entries: entries[f["name"]] = f
    local = work / "library"; local.mkdir(parents=True, exist_ok=True)
    have_json = {n[:-5] for n in entries if n.endswith(".json") and not n.endswith(".hub.json")}
    ls = _load("library-sync"); pi = _load("passage-import")
    for name, f in entries.items():
        p = pathlib.Path(name)
        if name.endswith(".json") and not name.endswith(".hub.json"):
            drv.download(f["id"], local / name)
        elif p.suffix.lower() in BOOK_EXT and pi.slugify(ls.title_author(p)[0]) not in have_json:
            log(f"library: new book {name} — downloading for import"); drv.download(f["id"], local / name)
    LIB.mkdir(exist_ok=True)
    needs_import = any(pathlib.Path(n).suffix.lower() in BOOK_EXT and pi.slugify(ls.title_author(pathlib.Path(n))[0]) not in have_json for n in entries)
    if needs_import and not (REPO / ".venv-tools" / "bin" / "markitdown").exists() and not dry:
        if run(["bash", SCRIPTS / "cloud-setup.sh", "--tools"]) != 0: log("library: markitdown install FAILED — import skipped this run")
    before = {x.name for x in local.iterdir()}
    phone = work / "phone"; phone.mkdir(exist_ok=True)
    done = ls.sync(local, LIB, pi, log=log, phone_dir=phone, shelf=[])   # imports + mirrors into REPO/library; the phone is stocked below, Drive-side
    if not dry:
        for x in sorted(local.iterdir()):
            if x.name not in before or (x.name.endswith(".json") and x.name.replace(".json", "") in done.get("imported", [])):
                try: log(f"library: uploading {x.name}"); drv.upload(x, lib_folder["id"])
                except SystemExit as e:
                    log(f"library: upload of {x.name} refused ({str(e)[:80]}…) — a service account owns what it creates and has no Drive quota; the passages are rebuilt from the EPUB each run instead")
                    break
    # Hub documents for a newly imported book: written locally (gitignored) for the Routine to write_db from files
    for slug in done.get("imported", []):
        src = LIB / f"{slug}.json"
        if src.exists():
            out = LIB / "hub" / slug; out.mkdir(parents=True, exist_ok=True)
            n = len(pi.write_hub_docs(json.loads(src.read_text(encoding="utf-8")), out))
            log(f"library: hub docs for {slug} ready in library/hub/{slug} ({n} + meta-book.json) — write_db them to the Hub (book/<id>, meta/book)")
    # the phone folder: exactly the shelf's EPUBs (Drive-side copies), sqlite files untouched
    shelf = load_json(REPO / "logs" / "reading" / "shelf.json", {}).get("phone") or []
    kfolder = drv.resolve("EnglishPractice/koreader")
    if kfolder and not dry:
        kids = {f["name"]: f for f in drv.children(kfolder["id"])}
        wanted = {n: f for n, f in entries.items() if pathlib.Path(n).suffix.lower() in BOOK_EXT and pi.slugify(ls.title_author(pathlib.Path(n))[0]) in shelf}
        for n, f in wanted.items():
            if n in kids: continue
            try: log(f"phone: + {n}"); drv.copy(f["id"], kfolder["id"], n)
            except SystemExit as e: log(f"phone: cannot copy {n} ({str(e)[:60]}…) — drop the EPUB into EnglishPractice/koreader yourself; the service account has no Drive quota")
        for n, f in kids.items():
            if pathlib.Path(n).suffix.lower() in BOOK_EXT and n not in wanted:
                try: log(f"phone: - {n}"); drv.trash(f["id"])
                except SystemExit as e: log(f"phone: cannot remove {n} ({str(e)[:60]}…) — remove it from EnglishPractice/koreader yourself")
    return done

def sync_recordings(drv, work, log=print, dry=False, skip_audio=False):
    """New audio under the recording roots → work/recordings; returns the number downloaded."""
    state = load_json(DRIVE_STATE, {})
    dest = work / "recordings"; n = 0
    for root in RECORDING_ROOTS:
        folder = drv.resolve(root)
        if not folder: log(f"recordings: {root} not visible — skipped"); continue
        for rel, f in drv.walk(folder["id"]):
            if pathlib.Path(rel).suffix.lower() not in AUDIO_EXT: continue
            seen = state.get(f["id"])
            if seen and seen.get("md5") == f.get("md5Checksum"): continue
            log(f"recordings: new {rel} ({f.get('size', '?')} B)")
            if dry or skip_audio: continue
            drv.download(f["id"], dest / rel)
            state[f["id"]] = {"name": rel, "md5": f.get("md5Checksum"), "size": f.get("size"), "modified": f.get("modifiedTime")}
            n += 1
    if not dry and n: dump_json(DRIVE_STATE, state)
    return n

def sync_reading(drv, work, log=print, dry=False):
    """The phone's KOReader databases when they changed → koreader-pull --dir."""
    folder = drv.resolve("EnglishPractice/koreader")
    if not folder: log("reading: EnglishPractice/koreader not visible — skipped"); return False
    state = load_json(READING_STATE, {}); dest = work / "koreader"; changed = False
    for f in drv.children(folder["id"]):
        if f["name"] not in ("vocabulary_builder.sqlite3", "statistics.sqlite3"): continue
        if state.get(f["name"]) == f.get("md5Checksum"): continue
        log(f"reading: {f['name']} changed"); changed = True
        if not dry: drv.download(f["id"], dest / f["name"]); state[f["name"]] = f.get("md5Checksum")
    if changed and not dry: dump_json(READING_STATE, state)
    return changed

def main():
    a = sys.argv[1:]
    if "--selftest" in a: return selftest()
    dry, skip_audio, push = "--dry-run" in a, "--skip-audio" in a, "--no-push" not in a
    d = _load("drive"); key = d.load_key()
    if not key: print("cloud-sync: GDRIVE_SA_JSON_B64 not set — nothing to do"); return 3
    drv = Drive(key)
    work = pathlib.Path(tempfile.mkdtemp(prefix="cloud-sync-"))
    print(f"== cloud-sync (work {work}) ==")
    try: sync_library(drv, work, dry=dry)
    except (SystemExit, Exception) as e:   # the shelf must never block the recordings
        print(f"cloud-sync: library step failed — {type(e).__name__}: {str(e)[:200]}")
    n = sync_recordings(drv, work, dry=dry, skip_audio=skip_audio)
    if n and not skip_audio:
        if run(["bash", SCRIPTS / "cloud-setup.sh"]) != 0: print("cloud-sync: practice venv FAILED — recordings left for next run"); n = 0
    if n and not skip_audio:
        env = {**os.environ, "PATH": f"{REPO / '.venv-practice' / 'bin'}:{os.environ.get('PATH', '')}"}
        if run([REPO / ".venv-practice" / "bin" / "python", SCRIPTS / "practice-ingest.py", "--source", work / "recordings"], env=env) != 0:
            print("cloud-sync: practice ingest FAILED")
        run([sys.executable, SCRIPTS / "practice-review.py"])
    if sync_reading(drv, work, dry=dry) and not dry:
        run([sys.executable, SCRIPTS / "koreader-pull.py", "--dir", work / "koreader"])
    elif not dry:
        run([sys.executable, SCRIPTS / "koreader-pull.py"])   # kosync position, if its credentials exist
    if not dry:
        run([sys.executable, SCRIPTS / "reading-cards.py"])
        run([sys.executable, SCRIPTS / "anki-cloud.py"])
        run([sys.executable, SCRIPTS / "reading-hub.py"])
        run(["git", "-C", REPO, "add", "logs/", "cards/", "drills/"])
        if subprocess.run(["git", "-C", str(REPO), "diff", "--cached", "--quiet"]).returncode == 0:
            print("cloud-sync: nothing new — no commit")
        else:
            run(["git", "-C", REPO, "commit", "-q", "-m", "observations: cloud sync"])
            if push: run(["git", "-C", REPO, "push", "-q", "origin", "HEAD"])
            print("cloud-sync: committed" + (" + pushed" if push else ""))
    shutil.rmtree(work, ignore_errors=True)
    return 0

class FakeDrive:
    """A folder tree as Drive: ids are relative paths; md5 = real md5 of the file."""
    FOLDER = "application/vnd.google-apps.folder"
    def __init__(self, root): self.root = pathlib.Path(root); self.trashed = []; self.copied = []
    def _f(self, p):
        rel = str(p.relative_to(self.root)); st = p.stat() if p.is_file() else None
        return {"id": rel, "name": p.name, "mimeType": self.FOLDER if p.is_dir() else "application/octet-stream",
                "size": str(st.st_size) if st else None, "md5Checksum": hashlib.md5(p.read_bytes()).hexdigest() if st else None, "modifiedTime": "2026-09-10T00:00:00Z"}
    def resolve(self, path): p = self.root / path; return self._f(p) if p.exists() else None
    def children(self, fid): return [self._f(x) for x in sorted((self.root / fid).iterdir())]
    def walk(self, fid):
        base = self.root / fid
        return [(str(x.relative_to(base)), self._f(x)) for x in sorted(base.rglob("*")) if x.is_file()]
    def download(self, fid, dest): dest = pathlib.Path(dest); dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(self.root / fid, dest); return dest
    def upload(self, path, fid, name=None): shutil.copyfile(path, self.root / fid / (name or pathlib.Path(path).name)); return {"name": name or pathlib.Path(path).name}
    def copy(self, fid, folder_id, name=None): self.copied.append(fid); shutil.copyfile(self.root / fid, self.root / folder_id / (name or pathlib.Path(fid).name))
    def trash(self, fid): self.trashed.append(fid); (self.root / fid).unlink()

def selftest():
    global DRIVE_STATE, READING_STATE, LIB, REPO_SHELF
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td); root = td / "drive"; (root / "EnglishPractice" / "library").mkdir(parents=True)
        (root / "EnglishPractice" / "koreader").mkdir(); (root / "EnglishPractice" / "Recordings" / "sub").mkdir(parents=True)
        (root / "EnglishPractice" / "library" / "Test_Author__A_Small_Book.txt").write_text("# Chapter One\n\n" + ("The morning was cold and the station was already full of people who did not look at each other. " * 12).strip() + "\n")
        (root / "EnglishPractice" / "koreader" / "statistics.sqlite3").write_bytes(b"s1"); (root / "EnglishPractice" / "koreader" / "Old__Gone.epub").write_bytes(b"e")
        (root / "EnglishPractice" / "Recordings" / "sub" / "eng read.m4a").write_bytes(b"audio"); (root / "EnglishPractice" / "Recordings" / "notes.txt").write_bytes(b"x")
        drv = FakeDrive(root); work = td / "work"; work.mkdir()
        # hermetic state + library locations
        DRIVE_STATE = td / "drive-state.json"; READING_STATE = td / "reading-state.json"; LIB = td / "lib"; LIB.mkdir()
        pi = _load("passage-import"); pi.BOOKS = td / "books.json"
        import types
        # shelf: the small book on the phone
        shelf_path = td / "shelf.json"; shelf_path.write_text(json.dumps({"phone": ["a-small-book"]}))
        real_load_json = load_json
        globals()["load_json"] = lambda p, default: real_load_json(shelf_path if str(p).endswith("shelf.json") else p, default)
        logs = []
        done = sync_library(drv, work, log=logs.append)
        assert done["imported"] == ["a-small-book"], done      # Old__Gone.epub (fake bytes) is skipped with a log line, not a crash
        assert any("Old__Gone.epub could not be converted" in l for l in logs), logs
        names = {f["name"] for f in drv.children("EnglishPractice/library")}
        assert "a-small-book.json" in names and "a-small-book.hub.json" in names, names
        knames = {f["name"] for f in drv.children("EnglishPractice/koreader")}
        assert "Test_Author__A_Small_Book.txt" in knames and "Old__Gone.epub" not in knames and "statistics.sqlite3" in knames, knames
        assert drv.copied == ["EnglishPractice/library/Test_Author__A_Small_Book.txt"] and drv.trashed == ["EnglishPractice/koreader/Old__Gone.epub"]
        n = sync_recordings(drv, work, log=logs.append)
        assert n == 1 and (work / "recordings" / "sub" / "eng read.m4a").read_bytes() == b"audio", n
        assert sync_recordings(drv, work, log=logs.append) == 0, "second pass: nothing new"
        assert sync_reading(drv, work, log=logs.append) is True and (work / "koreader" / "statistics.sqlite3").exists()
        assert sync_reading(drv, work, log=logs.append) is False
        (root / "EnglishPractice" / "koreader" / "statistics.sqlite3").write_bytes(b"s2")
        assert sync_reading(drv, work, log=logs.append) is True, "changed md5 → downloaded again"
        globals()["load_json"] = real_load_json
    print("cloud-sync.py selftest: OK")

if __name__ == "__main__":
    sys.exit(main())
