#!/usr/bin/env python3
"""The bookshelf: Drive `EnglishPractice/library/` ↔ the repo's gitignored `library/`.

    python3 scripts/library-sync.py                 # Mac: uses the Google Drive desktop mount
    python3 scripts/library-sync.py --drive <dir>   # any folder that plays the Drive role
    python3 scripts/library-sync.py --selftest

Drop an EPUB (or .txt/.md) named `Author__Title.epub` into the Drive folder. This script, run by
the Mac's nightly job and by the recording watcher before each ingest:
  1. imports every book that has no `<slug>.json` yet (scripts/passage-import.py: ~150-word
     passages B001…; the book's KOReader document ids go to logs/reading/books.json — hashes,
     never text), writing `<slug>.json` next to the EPUB in Drive and into the repo's `library/`;
  2. writes `<slug>.hub.json` beside it — the bundle the Hub's Read tab imports with one tap
     ("Import a book…"), so the Hub gets the passages without the text crossing the cloud session;
  3. copies any `<slug>.json` that exists on one side only to the other side, so the passage
     detection of the ingest always sees every book;
  4. stocks the phone: logs/reading/shelf.json (committed — the coach edits it from the cloud) lists
     the slugs the phone should hold; their EPUBs are copied into Drive `EnglishPractice/koreader/`,
     the folder the phone mirrors two-way into `koreader/settings/` (Autosync), and EPUBs no longer
     on the shelf are removed from it. Only *.epub/.txt/.md are ever touched there — the sqlite
     files KOReader writes are read by koreader-pull.py and never written.
Copyrighted text lives in Drive (private) and on the two machines' disks, never in git.
"""
import importlib.util, json, pathlib, shutil, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
LIB = REPO / "library"
SHELF = REPO / "logs" / "reading" / "shelf.json"
BOOK_EXT = (".epub", ".txt", ".md")

def _pi():
    spec = importlib.util.spec_from_file_location("passage_import", REPO / "scripts" / "passage-import.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def drive_dirs():
    home = pathlib.Path.home()
    return [m / "My Drive" / "EnglishPractice" / "library" for m in sorted((home / "Library/CloudStorage").glob("GoogleDrive-*"))]

def find_drive(explicit=None):
    for d in ([pathlib.Path(explicit)] if explicit else []) + drive_dirs():
        if d.is_dir(): return d
    return None

def title_author(path):
    """`Author__Title.epub` or `Author - Title.epub` → (title, author); `Title.epub` → (title, "")."""
    stem = path.stem
    for sep in ("__", " - "):
        if sep in stem:
            a, t = stem.split(sep, 1)
            return t.replace("_", " ").strip(), a.replace("_", " ").strip()
    return stem.replace("_", " ").strip(), ""

def bundle(book, pi):
    """Everything the Hub page needs to store the book: meta/book + the chapter documents."""
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        ids = pi.write_hub_docs(book, td)
        docs = {did: json.loads((td / f"book-{did}.json").read_text(encoding="utf-8")) for did in ids}
        meta = json.loads((td / "meta-book.json").read_text(encoding="utf-8"))
    return {"slug": pi.slugify(book["title"]), "title": book["title"], "meta": meta, "docs": docs}

def stock_phone(drive, phone_dir, shelf, pi, log=print):
    """Make the phone folder hold exactly the shelf's books (by slug of Author__Title). Returns (added, removed)."""
    if not phone_dir.is_dir():
        log(f"library-sync: phone folder {phone_dir} missing — create the Autosync pair first"); return [], []
    wanted = {}
    for src in drive.iterdir():
        if src.suffix.lower() in BOOK_EXT and not src.name.startswith("."):
            t, _a = title_author(src)
            if pi.slugify(t) in shelf: wanted[src.name] = src
    added, removed = [], []
    for name, src in wanted.items():
        dst = phone_dir / name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copyfile(src, dst); added.append(name)
    for f in phone_dir.iterdir():
        if f.suffix.lower() in BOOK_EXT and f.name not in wanted and not f.name.startswith("."):
            f.unlink(); removed.append(f.name)
    missing = [s for s in shelf if s not in {pi.slugify(title_author(p)[0]) for p in wanted.values()}]
    if missing: log(f"library-sync: on the shelf but no EPUB in Drive library/: {missing}")
    return added, removed

def sync(drive, lib=LIB, pi=None, log=print, phone_dir=None, shelf=None):
    pi = pi or _pi()
    lib.mkdir(exist_ok=True)
    done = {"imported": [], "copied_down": [], "copied_up": []}
    for src in sorted(p for p in drive.iterdir() if p.suffix.lower() in BOOK_EXT and not p.name.startswith(".")):
        title, author = title_author(src)
        slug = pi.slugify(title)
        if (drive / f"{slug}.json").exists() or (lib / f"{slug}.json").exists(): continue
        log(f"library-sync: importing {src.name} → {slug}")
        book = pi.build(pi.to_markdown(src), title, author, src.name, 150)
        if not book["chunks"]:
            log(f"library-sync: {src.name} produced no passages — skipped (check the file)"); continue
        text = json.dumps(book, ensure_ascii=False, indent=1) + "\n"
        (lib / f"{slug}.json").write_text(text, encoding="utf-8")
        (drive / f"{slug}.json").write_text(text, encoding="utf-8")
        (drive / f"{slug}.hub.json").write_text(json.dumps(bundle(book, pi), ensure_ascii=False) + "\n", encoding="utf-8")
        pi.register_book(src, slug, title, author, len(book["chunks"]))
        done["imported"].append(slug)
    for f in sorted(drive.glob("*.json")):
        if f.name.endswith(".hub.json") or (lib / f.name).exists(): continue
        shutil.copyfile(f, lib / f.name); done["copied_down"].append(f.stem)
    for f in sorted(lib.glob("*.json")):
        if (drive / f.name).exists(): continue
        shutil.copyfile(f, drive / f.name); done["copied_up"].append(f.stem)
    phone_dir = phone_dir if phone_dir is not None else drive.parent / "koreader"
    shelf = shelf if shelf is not None else (json.loads(SHELF.read_text(encoding="utf-8")).get("phone") if SHELF.exists() else [])
    done["phone_added"], done["phone_removed"] = stock_phone(drive, phone_dir, shelf or [], pi, log)
    return done

def selftest():
    pi = _pi()
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td); drive = td / "drive"; lib = td / "lib"; drive.mkdir()
        pi.BOOKS = td / "books.json"
        (drive / "Test_Author__A_Small_Book.txt").write_text("# Chapter One\n\n" + ("The morning was cold and the station was already full of people who did not look at each other. " * 12).strip() + "\n\n# Chapter Two\n\nA short one. It ends here.\n")
        (lib / "x").parent.mkdir(); (lib / "older-book.json").write_text('{"title": "Older", "chunks": []}')
        phone = td / "koreader"; phone.mkdir(); (phone / "statistics.sqlite3").write_bytes(b"x"); (phone / "Old__Gone.epub").write_bytes(b"y")
        d = sync(drive, lib, pi, log=lambda *a: None, phone_dir=phone, shelf=["a-small-book"])
        assert d == {"imported": ["a-small-book"], "copied_down": [], "copied_up": ["older-book"], "phone_added": ["Test_Author__A_Small_Book.txt"], "phone_removed": ["Old__Gone.epub"]}, d
        assert (phone / "statistics.sqlite3").exists() and (phone / "Test_Author__A_Small_Book.txt").exists(), "the phone folder holds the shelf's books and nothing else of ours; sqlite untouched"
        assert (drive / "a-small-book.json").exists() and (lib / "a-small-book.json").exists() and (drive / "older-book.json").exists()
        b = json.loads((drive / "a-small-book.hub.json").read_text())
        assert b["meta"]["title"] == "A Small Book" and b["meta"]["chapters"][0]["first"] == "B001" and list(b["docs"])[0].startswith("01-") and b["docs"][list(b["docs"])[0]]["chunks"][0]["id"] == "B001", b["meta"]
        reg = json.loads(pi.BOOKS.read_text()); assert reg[0]["slug"] == "a-small-book" and reg[0]["author"] == "Test Author" and len(reg[0]["partial_md5"]) == 32, reg
        (lib / "a-small-book.json").unlink()
        d = sync(drive, lib, pi, log=lambda *a: None, phone_dir=phone, shelf=[])
        assert d["copied_down"] == ["a-small-book"] and d["phone_removed"] == ["Test_Author__A_Small_Book.txt"] and (lib / "a-small-book.json").exists(), d
        assert title_author(pathlib.Path("Only_Title.epub")) == ("Only Title", "")
        assert title_author(pathlib.Path("Hannah Arendt - The Origins of Totalitarianism.epub")) == ("The Origins of Totalitarianism", "Hannah Arendt")
    print("library-sync.py selftest: OK")

def main():
    if "--selftest" in sys.argv: return selftest()
    drive = find_drive(sys.argv[sys.argv.index("--drive") + 1] if "--drive" in sys.argv else None)
    if not drive:
        print("library-sync: no Drive library folder on this machine — skipped"); return 3
    d = sync(drive)
    print(f"library-sync ({drive}): imported {d['imported'] or 'nothing'}, down {d['copied_down'] or '-'}, up {d['copied_up'] or '-'}, phone +{d['phone_added'] or '-'} -{d['phone_removed'] or '-'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
