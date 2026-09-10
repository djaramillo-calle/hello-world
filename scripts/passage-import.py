#!/usr/bin/env python3
"""Turn a book (EPUB/PDF/DOCX/HTML/Markdown) into read-aloud passages.

    python3 scripts/passage-import.py <book.epub|book.md> [--title "..."] [--author "..."] [--words 150]
    python3 scripts/passage-import.py --selftest

Output: library/<slug>.json — the book cut into ~150-word passages (B001, B002, …) that end
on sentence boundaries, grouped by chapter, with the running headers, footnote marks and
OCR dropped-cap artefacts of scanned editions cleaned up. `library/` is gitignored: the text
is copyrighted and stays on this machine and in the private Hub store (see --hub-docs).

    --hub-docs <dir>   also write the documents the Hub's Read tab reads: one JSON per chapter
                       (collection `book`, ≤ 200 KB each) plus meta-book.json (the table of contents)
    --md <file.md>     use an existing Markdown conversion instead of running markitdown

Conversion uses the `markitdown` CLI when the input is not Markdown (pip install "markitdown[epub]"
in any venv; the practice venv is fine). The passages are read aloud and scored against their
text (docs/PRACTICE.md), so the cut favours clean sentence ends over exact length.
"""
import argparse, datetime as dt, json, pathlib, re, shutil, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
LIB = REPO / "library"
PART = 110   # passages per Hub document (~150 KB, under the 256 KiB document limit)
SKIP_SECTIONS = ("INDEX", "BIBLIOGRAPHY", "CONTENTS", "ACKNOWLEDGMENTS", "ACKNOWLEDGEMENTS")

CAPWORD = r"[A-Z][A-Z0-9'’\-—.,;:]+"          # a header word: two or more capitals (a dropped cap "T HE" is not one)
NUM = r"(?:[xivlcXIVLC]{1,7}|\d{1,4})"
HEADER_RX = [
    re.compile(r"^\s*" + NUM + r"\s*[.;:,]?\s+((?:" + CAPWORD + r"\s+)+)"),       # "xii PREFACE TO PART ONE was…"
    re.compile(r"^\s*((?:" + CAPWORD + r"\s+)+)[.;:,]?\s*" + NUM + r"\s*[.;:,]?\s+"),      # "THE JEWS AND SOCIETY 59 Mendelssohn…", "… EDITION . ix appears"
]
CHAPTER_RX = re.compile(r"^\s*(?:PART\s+[A-Z]+\s*[:.]?\s*)?C[HU]{1,2}APTER\s+([A-Z]+)\s*[:?.\-—]*\s*(.{3,120})")
NUMBER_WORDS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6, "SEX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9,
                "TEN": 10, "ELEVEN": 11, "TWELVE": 12, "THIRTEEN": 13, "FOURTEEN": 14, "FIFTEEN": 15}
PREFACE_RX = re.compile(r"^\s*(?:[xivlcXIVLC]{1,7}\s+)?(PREFACE(?: TO(?: [A-Z]{2,})+)?)")
ROMAN = re.compile(r"^[xivlcXIVLC]+$")

def chapter_title(rest: str) -> str:
    """The title runs until the chapter's first words: a numbered subsection ('1: The Facts'), an all-caps
    opener ('ANY STILL', 'AZISM AND'), a dropped cap ('T HE', 'O= THE', 'F RACE-THINKING') or OCR junk."""
    m = re.search(r"\s+(?=(?:\d\s*[:!.]\s|[A-Z][A-Za-z=:]?\s+[A-Z]{2,}|[A-Z]{3,}[\s-][A-Z]{2,}|\\|wo\s+NEw|\|))", rest)
    t = rest[:m.start()] if m else rest
    return t.strip(" :.-—?\\|")

def preface_title(raw: str) -> str:
    words = [w for w in raw.split() if not ROMAN.match(w)]
    return " ".join(words).title()

def to_markdown(path: pathlib.Path) -> str:
    if path.suffix.lower() in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="replace")
    exe = shutil.which("markitdown") or next((str(p) for p in [REPO / ".venv-practice/bin/markitdown"] if p.exists()), None)
    if not exe:
        sys.exit("markitdown not found: pip install 'markitdown[epub]' (in the practice venv) or pass --md <converted.md>")
    return subprocess.run([exe, str(path)], check=True, capture_output=True, text=True).stdout

def clean_page(text: str) -> str:
    """One scanned page → readable prose. Strips the running header, footnote marks and OCR artefacts."""
    t = text.strip()
    for rx in HEADER_RX:
        m = rx.match(t)
        if m:
            t = t[m.end():]
            break
    t = re.sub(r"\\\*\d*", "", t)                          # markdown-escaped asterisks used as footnote marks
    t = re.sub(r"(?<=[a-zA-Z.,;:!?’”)])\d{1,3}(?=[\s.,;:!?’”)])", "", t)   # trailing footnote numbers: "policy.15 Moreover"
    t = re.sub(r"\b([A-Z])\s+([A-Z]{2,})\b", lambda m: m.group(1) + m.group(2).lower(), t)   # dropped caps: "T HE JEWS" → "The JEWS"
    t = re.sub(r"\b([A-Z][a-z]+)\s+([A-Z]{3,}(?:\s+[A-Z]{2,}){0,3})\b", lambda m: m.group(1) + " " + m.group(2).lower(), t)  # "The JEWS' political" → "The jews' political"
    t = re.sub(r"[|¦]\s*[:;.]?\s*", "", t)                   # OCR bars
    t = re.sub(r"\s+", " ", t)
    return t.strip()

def sentences(text: str):
    parts = re.split(r"(?:(?<=[.!?])|(?<=[.!?][’”\")\]]))\s+(?=[A-Z“‘(\d])", text)
    return [p.strip() for p in parts if p.strip()]

NOTE_RX = re.compile(r"(?:\bop\. ?cit\b|\bibid\b|\bloc\. ?cit\b|\bpp?\. ?\d|\bvol\. ?[IVX\d]|\bed\.,|\bcf\. |\(\d{4}\)|,\s*(?:19|18)\d\d[,.;)]|\b(?:London|Paris|Berlin|New York|Cambridge|Oxford|Leipzig|Wien|Munich|München),\s*(?:19|18)\d\d)", re.I)
NOTE_START_RX = re.compile(r"^\d{1,3}\s*[“\"A-Z(]")

def is_note(sentence: str) -> bool:
    """A footnote sentence from a scanned page (they sit at the page foot in the same text block):
    starts with a note number, or carries a citation marker. Read-aloud passages are body prose only."""
    return bool(NOTE_START_RX.match(sentence)) or bool(NOTE_RX.search(sentence))

def chunk(sents, target=150, lo=None, hi=None):
    lo = lo or int(target * 0.75); hi = hi or int(target * 1.35)
    out, cur, n = [], [], 0
    for s in sents:
        w = len(s.split())
        if cur and n + w > hi and n >= lo:
            out.append(" ".join(cur)); cur, n = [], 0
        cur.append(s); n += w
        if n >= target:
            out.append(" ".join(cur)); cur, n = [], 0
    if cur:   # a short tail joins the previous passage unless that makes it unreadably long
        if out and n < lo and len(out[-1].split()) + n <= int(hi * 1.25):
            out[-1] = out[-1] + " " + " ".join(cur)
        else:
            out.append(" ".join(cur))
    return out

def sections(md: str):
    """Yield (title, [page texts]) in reading order. Front matter before the first preface/chapter is dropped,
    back matter (index, bibliography) too. Works on page-per-line scans and on structured Markdown alike."""
    lines = [l for l in md.split("\n") if l.strip() and not l.startswith("**Identifier:**")]
    cur_title, cur, started = None, [], False
    def flush():
        nonlocal cur
        if cur_title and cur and not any(cur_title.upper().startswith(s) for s in SKIP_SECTIONS):
            yield_list.append((cur_title, cur))
        cur = []
    yield_list = []
    expanded, split_done = [], False
    for raw in lines:
        m = None if split_done else re.search(r"\bPreface to the (?:First|Second|Third) Edition\b", raw)
        if m and m.start() > 0 and m.start() < 600:
            split_done = True
            expanded.append(raw[:m.start()]); expanded.append(raw[m.start():].upper()[:len(m.group(0))] + raw[m.end():])
        else:
            expanded.append(raw)
    lines = expanded
    for raw in lines:
        l = raw.strip().lstrip("#").strip()
        head = l[:140]
        title = None
        m = CHAPTER_RX.match(head)
        if m:
            n = NUMBER_WORDS.get(m.group(1).upper())
            title = f"Chapter {n if n else m.group(1).title()}: {chapter_title(m.group(2))}"
        elif PREFACE_RX.match(head):
            pm = PREFACE_RX.match(head)
            p = preface_title(pm.group(1))
            if cur_title != p: title = p
        elif re.match(r"^\s*(?:INDEX|BIBLIOGRAPHY)\b", head):
            title = head.split()[0].title()
        if title:
            flush(); cur_title, started = title, True
            # the chapter's own text follows the heading on the same page
            body = l[m.start(2) + len(m.group(2)) - len(m.group(2).lstrip()) + len(chapter_title(m.group(2))):] if m else re.sub(r"^\s*[.;:,]?\s*" + NUM + r"\b\s*[.;:,]?\s*", "", l[pm.end():])
            if body.strip(): cur.append(body)
            continue
        if started:
            cur.append(l)
    flush()
    return yield_list

def build(md: str, title: str, author: str, source: str, words=150):
    chunks, chapters = [], []
    for order, (sec_title, pages) in enumerate(sections(md), 1):
        text = " ".join(clean_page(p) for p in pages)
        pieces = chunk([x for x in sentences(text) if not is_note(x)], words)
        first = len(chunks) + 1
        for piece in pieces:
            chunks.append({"id": f"B{len(chunks) + 1:03d}", "chapter": sec_title, "words": len(piece.split()), "text": piece})
        chapters.append({"order": order, "title": sec_title, "first": f"B{first:03d}", "last": f"B{len(chunks):03d}", "n": len(pieces)})
    return {"title": title, "author": author, "source": source, "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "target_words": words, "chapters": chapters, "chunks": chunks}

def slugify(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]

def write_hub_docs(book, out_dir: pathlib.Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    by = {}
    for c in book["chunks"]: by.setdefault(c["chapter"], []).append(c)
    docs = []
    meta_ch = []
    for ch in book["chapters"]:
        cl = by.get(ch["title"], [])
        parts = [cl[i:i + PART] for i in range(0, len(cl), PART)] or [[]]
        for pi, part in enumerate(parts):
            did = f"{ch['order']:02d}{chr(97 + pi) if len(parts) > 1 else ''}-{slugify(ch['title'])}"
            doc = {"title": ch["title"], "order": ch["order"], "part": pi + 1, "parts": len(parts),
                   "first": part[0]["id"] if part else ch["first"], "last": part[-1]["id"] if part else ch["last"], "chunks": part}
            (out_dir / f"book-{did}.json").write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8")
            docs.append(did)
            meta_ch.append({"order": ch["order"], "title": ch["title"], "doc": did, "first": doc["first"], "last": doc["last"], "n": len(part)})
    meta = {"title": book["title"], "author": book["author"], "generated": book["generated"], "total": len(book["chunks"]),
            "chapters": meta_ch}
    (out_dir / "meta-book.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return docs

def selftest():
    md = ("**Identifier:** x\n\nTHE BOOK\n\nCopyright 1951\n\n"
          "PREFACE TO THE FIRST EDITION . ix Two world wars in one generation have ended in anticipation. This is the reality in which we live.\\*3 "
          + " ".join(f"Sentence number {i} of the preface is here." for i in range(40)) + "\n\n"
          "CHAPTER ONE? Antisemitism as an Outrage to Common Sense M ANY STILL consider it an accident. " + " ".join(f"Chapter sentence {i} follows." for i in range(60)) + "\n\n"
          "14 ANTISEMITISM Jews neglected their chances.15 But without the industrial revolution nothing changed. " + " ".join(f"More text {i} here." for i in range(30)) + "\n\n"
          "INDEX in Soviet Russia, 296, 434\n")
    b = build(md, "T", "A", "t.md", words=40)
    titles = [c["title"] for c in b["chapters"]]
    assert titles[0] == "Preface To The First Edition" and titles[1] == "Chapter 1: Antisemitism as an Outrage to Common Sense", titles
    assert chapter_title("Race-Thinking Before Racism F RACE-THINKING were a German") == "Race-Thinking Before Racism"
    assert chapter_title("The Totalitarian Movement 1: Totalitarian Propaganda O= THE MOB and") == "The Totalitarian Movement"
    assert chapter_title("Race and Bureaucracy wo NEw DEVICES for") == "Race and Bureaucracy"
    assert chapter_title("The Dreyfus Affair 1: The Facts of the Case |: HAPPENED in") == "The Dreyfus Affair"
    assert chapter_title("Totalitarianism in Power \\ \\ / HEN A MOVEMENT, international") == "Totalitarianism in Power"
    assert chapter_title("Ideology and Terror: A Novel Form of Government Ir THE PRECEDING chapers") == "Ideology and Terror: A Novel Form of Government"
    assert preface_title("PREFACE TO PART THREE XXXV") == "Preface To Part Three"
    assert NUMBER_WORDS["SEX"] == 6
    assert all(c["chapter"] != "Index" for c in b["chunks"])
    t0 = b["chunks"][0]["text"]
    assert t0.startswith("Two world wars") and "\\*" not in t0 and ".3 " not in t0, t0[:120]
    c1 = next(c for c in b["chunks"] if c["chapter"].startswith("Chapter 1:"))["text"]
    assert c1.startswith("Many still consider"), c1[:80]
    later = " ".join(c["text"] for c in b["chunks"] if c["chapter"].startswith("Chapter 1:"))
    assert "14 ANTISEMITISM" not in later and "chances. But" in later, later[:300]
    assert all(25 <= c["words"] <= 60 for c in b["chunks"][:-1]), [c["words"] for c in b["chunks"]]
    assert all(c["text"].rstrip()[-1] in ".!?’”\")" for c in b["chunks"]), [c["text"][-20:] for c in b["chunks"]]
    assert is_note("7 Quoted from Merle Fainsod, How Russia Is Ruled, Cambridge, 1959, p. 516.") and is_note("See ibid., p. 12.") and not is_note("The streets were busy in 1959 and nobody noticed.")
    assert not is_note("Two world wars in one generation have ended in anticipation.")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        docs = write_hub_docs(b, pathlib.Path(td))
        assert len(docs) == 2 and (pathlib.Path(td) / "meta-book.json").exists()
    print("passage-import.py selftest: OK")

BOOKS = REPO / "logs" / "reading" / "books.json"

def register_book(path, slug, title, author, n_passages):
    """logs/reading/books.json: the book's KOReader document ids (partial MD5 of the file, MD5 of the
    filename) and passage count — what koreader-pull.py needs to map a reading position to a passage.
    Hashes and counts only; the text stays in library/."""
    import hashlib
    m = hashlib.md5()
    with open(path, "rb") as f:
        for i in range(-1, 11):
            f.seek(0 if i == -1 else 1024 << (2 * i))
            s = f.read(1024)
            if not s: break
            m.update(s)
    entry = {"slug": slug, "title": title, "author": author, "filename": path.name, "partial_md5": m.hexdigest(),
             "filename_md5": hashlib.md5(path.name.encode("utf-8")).hexdigest(), "passages": n_passages}
    try: books = json.loads(BOOKS.read_text(encoding="utf-8"))
    except (OSError, ValueError): books = []
    books = [b for b in books if b.get("slug") != slug and b.get("partial_md5") != entry["partial_md5"]] + [entry]
    BOOKS.parent.mkdir(parents=True, exist_ok=True)
    BOOKS.write_text(json.dumps(books, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return entry

def main():
    if "--selftest" in sys.argv: return selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("book", type=pathlib.Path)
    ap.add_argument("--title"); ap.add_argument("--author", default="")
    ap.add_argument("--words", type=int, default=150)
    ap.add_argument("--md", type=pathlib.Path, help="already-converted Markdown to use instead of running markitdown")
    ap.add_argument("--hub-docs", type=pathlib.Path, help="directory for the Hub documents (book/<chapter>, meta/book)")
    a = ap.parse_args()
    md = a.md.read_text(encoding="utf-8") if a.md else to_markdown(a.book)
    title = a.title or a.book.stem.replace("_", " ")
    book = build(md, title, a.author, a.book.name, a.words)
    LIB.mkdir(exist_ok=True)
    out = LIB / f"{slugify(title)}.json"
    out.write_text(json.dumps(book, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if a.book.exists(): register_book(a.book, slugify(title), title, a.author, len(book["chunks"]))
    ws = [c["words"] for c in book["chunks"]]
    print(f"{title}: {len(book['chapters'])} sections, {len(book['chunks'])} passages, {sum(ws)} words "
          f"(passage {min(ws) if ws else 0}–{max(ws) if ws else 0} words) → {out.relative_to(REPO)}")
    for ch in book["chapters"]: print(f"  {ch['first']}–{ch['last']}  {ch['title']}")
    if a.hub_docs:
        docs = write_hub_docs(book, a.hub_docs)
        print(f"hub docs: {len(docs)} chapter documents + meta-book.json in {a.hub_docs}")

if __name__ == "__main__":
    main()
