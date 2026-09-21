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
PAIRS_STATE = REPO / "logs" / "pairs" / ".drive.json"
PAIRS_PLAN = REPO / "logs" / "pairs" / "plan.json"
SAYIT_ZIP = REPO / "logs" / "sayit" / "sayit.zip"
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
    def resolve_all(self, path): return self.d.resolve_all(self.key, path)
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
    """New audio under the recording roots → work/recordings; returns (count, state-to-keep).

    The caller writes the state only once the INGEST has succeeded. Writing it here cost a whole
    recording on 2026-09-16: a `timeout` killed the run fifteen minutes into Whisper, the marker
    already said "downloaded", and the next run would have skipped a read that was never scored.
    A recording is the one thing in this pipeline that cannot be regenerated."""
    state = load_json(DRIVE_STATE, {})
    dest = work / "recordings"; n = 0
    seen_folders = set()
    for root in RECORDING_ROOTS:
        folders = drv.resolve_all(root) if hasattr(drv, "resolve_all") else [drv.resolve(root)]
        folders = [f for f in folders if f and f["id"] not in seen_folders]
        if not folders: log(f"recordings: {root} not visible — skipped"); continue
        for folder in folders:
          seen_folders.add(folder["id"])
          for rel, f in drv.walk(folder["id"]):
                if pathlib.Path(rel).suffix.lower() not in AUDIO_EXT: continue
                seen = state.get(f["id"])
                if seen and seen.get("md5") == f.get("md5Checksum"): continue
                log(f"recordings: new {rel} ({f.get('size', '?')} B)")
                if dry or skip_audio: continue
                drv.download(f["id"], dest / rel)
                state[f["id"]] = {"name": rel, "md5": f.get("md5Checksum"), "size": f.get("size"), "modified": f.get("modifiedTime")}
                n += 1
    return n, state

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

# Coach->app files live in the same folder and must never be pulled back down.
COACH_FILES = ("plan.json", "sayit.zip")
# Say-it attempt recordings. `sayit.py --score` falls back to scoring in the cloud when the phone
# could not (no key, no network, an error), and to do that it needs the audio sitting beside the
# sidecar. Until 2026-09-21 this function fetched only .json and .txt, so the audio never arrived
# and the fallback could not fire ONCE since it was written — four attempts of 2026-09-20 were
# skipped with "no audio beside it" while the .m4a sat on Drive. sayit.py was correct throughout;
# nothing tested the two together.
AUDIO_EXT = (".m4a", ".wav", ".mp3", ".ogg", ".opus", ".aac", ".flac")


def _attempt_audio(rel):
    return rel.startswith("sayit/attempts/") and rel.lower().endswith(AUDIO_EXT)


SAYIT_RESULTS = REPO / "logs" / "sayit" / "results.json"


def _sayit_done(path=None):
    """Attempt sidecar names already folded into results.json.

    The md5 state is the WRONG marker for Say-it. It says "downloaded once, ever", while the work
    directory it downloaded into is a temp dir wiped after every run — and in a fresh container it
    never existed. So a sidecar fetched on Monday is gone by Tuesday and never comes back, and on
    2026-09-21 the audio finally arrived into a work dir whose sidecars had been consumed days
    earlier: 0 scored, with both halves sitting on Drive.

    results.json is committed to git, so it is the only durable record of what has actually been
    scored. That is the marker."""
    d = load_json(path or SAYIT_RESULTS, {})
    return {a.get("file") for r in (d.get("words") or {}).values() for a in (r.get("attempts") or [])}


def _sayit_pending(rel, done):
    """True for a Say-it file whose attempt has not been scored yet — fetch it however old it is."""
    if not (rel.startswith("sayit/attempts/") or rel.startswith("sayit/scores/")):
        return False
    return (pathlib.PurePosixPath(rel).stem + ".json") not in done


PRACTICE_DIR = REPO / "logs" / "practice"


def _reads_done(practice=None):
    """Audio names of pages already ingested: the practice record's `source` is the durable marker
    (committed to git), for exactly the reason results.json is Say-it's."""
    out = set()
    for f in pathlib.Path(practice or PRACTICE_DIR).glob("*.json"):
        if f.name.startswith(".") or f.name.endswith(".review.json"): continue
        try: out.add(json.loads(f.read_text(encoding="utf-8")).get("source"))
        except Exception: pass
    return out


def _read_stem(rel):
    """`reads/<stem>.m4a|.json|.score.json` -> <stem>, else None."""
    if not rel.startswith("reads/"): return None
    name = rel.split("/", 1)[1]
    for ext in (".score.json", ".json", ".m4a", ".wav", ".mp3", ".ogg", ".opus", ".aac", ".flac"):
        if name.endswith(ext): return name[: -len(ext)]
    return None


def _read_pending(rel, done):
    """A page the app recorded (and maybe scored) that the coach has not ingested: all three files
    come down every run until the practice record exists."""
    stem = _read_stem(rel)
    if not stem: return False
    return not any(src and src.startswith(stem + ".") for src in done)


def sync_pairs(drv, work, log=print, dry=False, sayit_results=None, practice_dir=None):
    """The Minimal Pairs app's folder (Drive EnglishPractice/pairs ← phone Documents/MinimalPairs via Autosync):
    new session files, state.json and catalog-version.txt → work/pairs (folded by pairs-pull.py --dir).
    Returns True when something new came down."""
    folder = drv.resolve("EnglishPractice/pairs")
    if not folder: log("pairs: EnglishPractice/pairs not visible — skipped"); return False
    state = load_json(PAIRS_STATE, {}); dest = work / "pairs"; changed = False
    done = _sayit_done(sayit_results)
    reads_done = _reads_done(practice_dir)
    for rel, f in drv.walk(folder["id"]):
        if rel in COACH_FILES: continue                  # coach->app, never pulled back down
        if not (rel.endswith(".json") or rel.endswith(".txt") or _attempt_audio(rel) or _read_stem(rel) or rel.startswith("reading/")): continue
        # An unscored Say-it attempt comes down EVERY run, sidecar and audio together, until
        # results.json says it was scored. Everything else is fetched once by md5.
        if _sayit_pending(rel, done) or _read_pending(rel, reads_done):
            log(f"pairs: {rel} pending"); changed = True
            # the md5 is still recorded, so the ordinary path takes over the moment it is scored
            if not dry: drv.download(f["id"], dest / rel); state[rel] = f.get("md5Checksum")
            continue
        if state.get(rel) == f.get("md5Checksum"): continue
        log(f"pairs: {rel} new"); changed = True
        if not dry: drv.download(f["id"], dest / rel); state[rel] = f.get("md5Checksum")
    if changed and not dry: dump_json(PAIRS_STATE, state)
    return changed

def push_file(drv, local, remote_name, folder="EnglishPractice/pairs", log=print, dry=False):
    """Update a coach→app file in place. The service account has NO storage quota, so it can only PATCH a
    file that already exists — the owner creates each one once (plan.json 2026-09-11, sayit.zip 2026-09-13)."""
    local = pathlib.Path(local)
    if not local.exists(): return False
    f = drv.resolve(folder)
    if not f: return False
    remote = next((x for x in drv.children(f["id"]) if x["name"] == remote_name), None)
    if not remote:
        log(f"sayit: {remote_name} is not on Drive yet — the owner creates it once (docs/HUB.md)"); return False
    if remote.get("md5Checksum") == hashlib.md5(local.read_bytes()).hexdigest(): return False
    if dry: log(f"sayit: {remote_name} would be updated"); return True
    try: drv.upload(local, f["id"], name=remote_name); log(f"sayit: {remote_name} updated on Drive"); return True
    except Exception as e: log(f"sayit: {remote_name} NOT updated — {type(e).__name__}: {str(e)[:160]}"); return False

def push_plan(drv, log=print, dry=False, plan=None):
    """logs/pairs/plan.json → Drive EnglishPractice/pairs/plan.json when it differs (update in place:
    the file was created by the owner once, and the service account, with no quota of its own, can
    only PATCH an existing file — never create). The phone's Autosync carries it to the app."""
    plan = pathlib.Path(plan or PAIRS_PLAN)
    if not plan.exists(): return False
    folder = drv.resolve("EnglishPractice/pairs")
    if not folder: return False
    remote = next((f for f in drv.children(folder["id"]) if f["name"] == "plan.json"), None)
    if not remote: log("pairs: plan.json is not on Drive yet — the owner creates it once (see docs/HUB.md)"); return False
    if remote.get("md5Checksum") == hashlib.md5(plan.read_bytes()).hexdigest(): return False
    if dry: log("pairs: plan.json would be updated"); return True
    try: drv.upload(plan, folder["id"]); log("pairs: plan.json updated on Drive"); return True
    except Exception as e: log(f"pairs: plan.json NOT updated — {type(e).__name__}: {str(e)[:160]}"); return False

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
    n, rec_state = sync_recordings(drv, work, dry=dry, skip_audio=skip_audio)
    if n and not skip_audio:
        if run(["bash", SCRIPTS / "cloud-setup.sh"]) != 0: print("cloud-sync: practice venv FAILED — recordings left for next run"); n = 0
    if n and not skip_audio:
        env = {**os.environ, "PATH": f"{REPO / '.venv-practice' / 'bin'}:{os.environ.get('PATH', '')}"}
        if run([REPO / ".venv-practice" / "bin" / "python", SCRIPTS / "practice-ingest.py", "--source", work / "recordings"], env=env) != 0:
            print("cloud-sync: practice ingest FAILED — the recordings stay unmarked and come back next run")
        else:
            if not dry: dump_json(DRIVE_STATE, rec_state)   # marked downloaded ONLY once it is ingested
            run([sys.executable, SCRIPTS / "practice-review.py"])
    elif n and skip_audio and not dry:
        dump_json(DRIVE_STATE, rec_state)
    if sync_reading(drv, work, dry=dry) and not dry:
        run([sys.executable, SCRIPTS / "koreader-pull.py", "--dir", work / "koreader"])
    elif not dry:
        run([sys.executable, SCRIPTS / "koreader-pull.py"])   # kosync position, if its credentials exist
    try:
        if sync_pairs(drv, work, dry=dry) and not dry:
            run([sys.executable, SCRIPTS / "pairs-pull.py", "--dir", work / "pairs"])
            # The app's reader (its docs/CONTRACT.md, "Reader"): position, saved words, minutes —
            # folded into the same logs/reading files KOReader fed.
            if (work / "pairs" / "reading").is_dir():
                run([sys.executable, SCRIPTS / "reader-pull.py", "--dir", work / "pairs" / "reading"])
            # Pages read in the app: the audio, its sidecar and (usually) its phone score sit
            # together under work/pairs/reads. practice-ingest folds the phone score itself and
            # never calls Azure for these; the practice record it writes is what stops the
            # re-download. Whisper still runs, so the ingest needs the practice venv.
            reads = work / "pairs" / "reads"
            if reads.is_dir() and any(p.suffix.lower() in (".m4a", ".wav", ".mp3", ".ogg") for p in reads.iterdir()):
                if run(["bash", SCRIPTS / "cloud-setup.sh"]) == 0:
                    env = {**os.environ, "PATH": f"{REPO / '.venv-practice' / 'bin'}:{os.environ.get('PATH', '')}"}
                    if run([REPO / ".venv-practice" / "bin" / "python", SCRIPTS / "practice-ingest.py", "--source", reads], env=env) == 0:
                        run([sys.executable, SCRIPTS / "practice-review.py"])
                    else:
                        print("cloud-sync: app-read ingest FAILED — the pages come back next run")
        elif not dry:
            run([sys.executable, SCRIPTS / "pairs-pull.py", "--plan"])   # the ledger may have moved: keep the plan current
        push_plan(drv, dry=dry)
        # Say it: score the attempts he recorded, rebuild the word list from the ledger, ship one zip back
        if not dry:
            py = REPO / ".venv-practice" / "bin" / "python"           # scoring needs the Azure SDK + ffmpeg
            run([py if py.exists() else sys.executable, SCRIPTS / "sayit.py", "--score", "--dir", work / "pairs"])
            run([sys.executable, SCRIPTS / "sayit.py", "--build"])
            push_file(drv, SAYIT_ZIP, "sayit.zip", dry=dry)
    except (SystemExit, Exception) as e:   # the pairs app must never block the rest
        print(f"cloud-sync: pairs step failed — {type(e).__name__}: {str(e)[:200]}")
    if not dry:
        run([sys.executable, SCRIPTS / "reading-cards.py"])
        run([sys.executable, SCRIPTS / "anki-cloud.py"])
        run([sys.executable, SCRIPTS / "reading-hub.py"])
        run(["git", "-C", REPO, "add", "logs/", "cards/", "drills/"])
        if subprocess.run(["git", "-C", str(REPO), "diff", "--cached", "--quiet"]).returncode == 0:
            print("cloud-sync: nothing new — no commit")
        else:
            run(["git", "-C", REPO, "commit", "-q", "-m", "observations: cloud sync"])
            if push:
                # a probe session checks the branch out detached: push HEAD to the branch that contains it
                branch = subprocess.run(["git", "-C", str(REPO), "symbolic-ref", "--short", "-q", "HEAD"], capture_output=True, text=True).stdout.strip()
                if not branch:
                    refs = subprocess.run(["git", "-C", str(REPO), "for-each-ref", "--format=%(refname:short)", "--contains", "HEAD~1", "refs/remotes/origin"], capture_output=True, text=True).stdout.split()
                    branch = next((r.split("/", 1)[1] for r in refs if r.startswith("origin/") and r != "origin/HEAD"), "claude/adult-language-learning-gnk7i1")
                run(["git", "-C", REPO, "push", "-q", "origin", f"HEAD:{branch}"])
            print("cloud-sync: committed" + (f" + pushed to {branch}" if push else ""))
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
        n, st = sync_recordings(drv, work, log=logs.append)
        assert n == 1 and (work / "recordings" / "sub" / "eng read.m4a").read_bytes() == b"audio", n
        # the state is RETURNED, not written: an ingest that dies must not leave the recording marked
        assert not DRIVE_STATE.exists() or not json.loads(DRIVE_STATE.read_text()), "not written by the download"
        assert st and all("md5" in v for v in st.values()), st
        assert sync_recordings(drv, work, log=logs.append)[0] == 1, "unmarked: it comes back next run"
        dump_json(DRIVE_STATE, st)                                  # what the caller does once the ingest succeeded
        assert sync_recordings(drv, work, log=logs.append)[0] == 0, "marked: nothing new"
        assert sync_reading(drv, work, log=logs.append) is True and (work / "koreader" / "statistics.sqlite3").exists()
        assert sync_reading(drv, work, log=logs.append) is False
        (root / "EnglishPractice" / "koreader" / "statistics.sqlite3").write_bytes(b"s2")
        assert sync_reading(drv, work, log=logs.append) is True, "changed md5 → downloaded again"
        # pairs: sessions + state come down, plan.json never does; the plan goes up only when it differs and exists remotely
        global PAIRS_STATE
        PAIRS_STATE = td / "pairs-state.json"
        assert sync_pairs(drv, work, log=logs.append) is False and any("not visible" in l for l in logs)
        pf = root / "EnglishPractice" / "pairs"; (pf / "sessions").mkdir(parents=True)
        (pf / "sessions" / "20260911T070000Z.json").write_text('{"version": 1, "trials": []}'); (pf / "state.json").write_text('{"version": 1}')
        (pf / "plan.json").write_text('{"version": 1, "note": "old"}'); (pf / "clips.zip").write_bytes(b"zip")
        # a Say-it attempt the phone could not score: the SIDECAR ALONE IS USELESS. sayit.py's cloud
        # fallback globs for the audio beside it, so if this function skips the .m4a the attempt is
        # silently dropped with "no audio beside it" — which is exactly what happened to four
        # attempts on 2026-09-20 while the audio sat on Drive.
        (pf / "sayit" / "attempts").mkdir(parents=True)
        (pf / "sayit" / "attempts" / "20260920T202429Z_nazis.json").write_text('{"id": "nazis"}')
        (pf / "sayit" / "attempts" / "20260920T202429Z_nazis.m4a").write_bytes(b"audio")
        res = td / "results.json"
        res.write_text(json.dumps({"words": {"nazis": {"attempts": [{"file": "20260920T202429Z_nazis.json"}]}}}))
        assert sync_pairs(drv, work, log=logs.append, sayit_results=res) is True
        assert (work / "pairs" / "sessions" / "20260911T070000Z.json").exists() and (work / "pairs" / "state.json").exists()
        assert (work / "pairs" / "sayit" / "attempts" / "20260920T202429Z_nazis.m4a").read_bytes() == b"audio", \
            "attempt audio must come down or the cloud fallback can never fire"
        # An unscored attempt must come down AGAIN into a fresh work dir. The md5 state says
        # "fetched once, ever", but the work dir is temporary and a fresh container never had one,
        # so a sidecar fetched on a previous run is simply gone. results.json is the durable marker.
        work2 = td / "work2"; work2.mkdir()
        res.write_text(json.dumps({"words": {}}))
        assert sync_pairs(drv, work2, log=logs.append, sayit_results=res) is True
        assert (work2 / "pairs" / "sayit" / "attempts" / "20260920T202429Z_nazis.json").exists(), \
            "an unscored attempt must be re-fetched into a new work dir"
        assert (work2 / "pairs" / "sayit" / "attempts" / "20260920T202429Z_nazis.m4a").exists()
        # a page the app read and scored: all three files come down until a practice record names it
        (pf / "reads").mkdir()
        for n in ("20260921T092923Z_B110-B114.m4a", "20260921T092923Z_B110-B114.json", "20260921T092923Z_B110-B114.score.json"):
            (pf / "reads" / n).write_bytes(b"x")
        prac = td / "practice"; prac.mkdir()
        w4 = td / "work4"; w4.mkdir()
        assert sync_pairs(drv, w4, log=logs.append, sayit_results=res, practice_dir=prac) is True
        assert (w4 / "pairs" / "reads" / "20260921T092923Z_B110-B114.score.json").exists(), "the page must come down"
        (prac / "2026-09-21-x.json").write_text(json.dumps({"source": "20260921T092923Z_B110-B114.m4a", "kind": "read"}))
        w5 = td / "work5"; w5.mkdir()
        sync_pairs(drv, w5, log=logs.append, sayit_results=res, practice_dir=prac)
        assert not (w5 / "pairs" / "reads").exists(), "an ingested page must not be fetched again"
        # ...and stop coming down once results.json records it
        res.write_text(json.dumps({"words": {"nazis": {"attempts": [{"file": "20260920T202429Z_nazis.json"}]}}}))
        work3 = td / "work3"; work3.mkdir()
        sync_pairs(drv, work3, log=logs.append, sayit_results=res)
        assert not (work3 / "pairs" / "sayit").exists(), "a scored attempt must not be fetched again"
        assert not (work / "pairs" / "plan.json").exists() and not (work / "pairs" / "clips.zip").exists()
        # sayit.zip's exclusion is exercised by the push_file test below, which requires it absent here.
        # "nothing new" only once the attempt is scored — an UNSCORED one must keep coming down
        assert sync_pairs(drv, work, log=logs.append, sayit_results=res, practice_dir=prac) is False, "second pass: nothing new"
        local_plan = td / "plan.json"; local_plan.write_text('{"version": 1, "note": "new"}')
        assert push_plan(drv, log=logs.append, plan=local_plan) is True and (pf / "plan.json").read_text() == '{"version": 1, "note": "new"}'
        assert push_plan(drv, log=logs.append, plan=local_plan) is False, "same md5: no upload"
        (pf / "plan.json").unlink()
        assert push_plan(drv, log=logs.append, plan=local_plan) is False and any("not on Drive yet" in l for l in logs)
        # push_file only ever updates in place: a payload the owner has not created once is refused, not created
        zp = td / "sayit.zip"; zp.write_bytes(b"PK\x05\x06" + b"\0" * 18)
        assert push_file(drv, zp, "sayit.zip", log=logs.append) is False and any("sayit.zip is not on Drive yet" in l for l in logs)
        (pf / "sayit.zip").write_bytes(b"old")
        assert push_file(drv, zp, "sayit.zip", log=logs.append) is True and (pf / "sayit.zip").read_bytes() == zp.read_bytes()
        assert push_file(drv, zp, "sayit.zip", log=logs.append) is False, "same md5: no upload"
        globals()["load_json"] = real_load_json
    print("cloud-sync.py selftest: OK")

if __name__ == "__main__":
    sys.exit(main())
