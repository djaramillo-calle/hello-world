#!/usr/bin/env python3
"""epub-clean.py — apply the user's cleanup judgements to a scanned book (app repo docs/CONTRACT.md, "Cleanup").

    python3 scripts/epub-clean.py <slug> --epub <in.epub> --out <cleaned.epub>   # the EPUB and library/<slug>.json
    python3 scripts/epub-clean.py <slug> --dry-run                               # what would change, from the passages alone
    python3 scripts/epub-clean.py --selftest

The judgements are `logs/reading/cleanup.json` (reader-pull folds the phone's `reading/cleanup.jsonl`:
latest line per target wins): a `fix` replaces every whole-word occurrence, case preserved (Achicve →
Achieve); a `remove` deletes the word; a `head` removal deletes the running head wherever it is welded
into the text, with the page number after it, matched by letters alone so the EPUB's "A CLASSLESS
SOCIETY 307" and the passage file's "Aclassless society 307" are the same head; a `keep` changes
nothing and is remembered by the scanner. The EPUB is a page per XHTML file, so every page's own
running head ("THE DREYFUS AFFAIR 119 national misfortune…") is stripped too, by the same rule the
passage import already applied (`passage-import.HEADER_RX`) — the phone was still showing them.
The passage file is edited IN PLACE, chunk by chunk, so passage ids never move: the read pointer,
the ledger and the Say-it carriers keep pointing at the same text. The EPUB's partial MD5 changes;
`register_book` keeps the old hash as history so positions keyed by it still map."""
import importlib.util, json, pathlib, re, shutil, sys, tempfile, zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
LIB = REPO / "library"
DECISIONS = REPO / "logs" / "reading" / "cleanup.json"
TAG = re.compile(r"<[^>]+>")
FIRST_P = re.compile(r"(<p\b[^>]*>)(\s*)([^<]*)", re.S)

def _pi():
    spec = importlib.util.spec_from_file_location("passage_import", REPO / "scripts" / "passage-import.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def load_decisions(slug, path=DECISIONS):
    """{key: decision} for one slug, latest per target (reader-pull already kept only the latest)."""
    try: allb = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}
    return dict((allb.get(slug) or {}))

def _case_like(sample, fix):
    if sample.isupper() and len(sample) > 1: return fix.upper()
    if sample[:1].isupper(): return fix[:1].upper() + fix[1:]
    return fix

def word_re(target):
    return re.compile(r"(?<![A-Za-z])" + re.escape(target) + r"(?![A-Za-z])", re.I)

def head_re(phrase):
    """Letters with any spacing between them, then the page number: the head as any rendering shows it."""
    letters = [c for c in phrase if not c.isspace()]
    body = r"\s*".join(re.escape(c) for c in letters)
    return re.compile(r"(?<![A-Za-z])" + body + r"\s*[.;:,]?\s*\d{1,4}\b\s*[.;:,]?\s*", re.I)

def compile_rules(decisions):
    """(word rules, head rules) from the decisions: [(regex, fix or None)], [regex]."""
    words, heads = [], []
    for d in decisions.values():
        act = d.get("action"); target = (d.get("target") or "").strip()
        if not target or act == "keep": continue
        if d.get("kind") == "head":
            if act == "remove": heads.append(head_re(target))
            continue
        if act == "fix" and (d.get("fix") or "").strip(): words.append((word_re(target), d["fix"].strip()))
        elif act == "remove": words.append((word_re(target), None))
    return words, heads

def clean_text(text, words, heads, counts=None):
    """One string of prose → the same with the rules applied; counts what changed."""
    counts = counts if counts is not None else {}
    changed = False
    for rx in heads:
        text, n = rx.subn(" ", text)
        if n: counts["heads"] = counts.get("heads", 0) + n; changed = True
    for rx, fix in words:
        if fix is None:
            text, n = re.subn(r"\s*" + rx.pattern, "", text, flags=re.I)
        else:
            text, n = rx.subn(lambda m: _case_like(m.group(0), fix), text)
        if n: counts["words"] = counts.get("words", 0) + n; changed = True
    # only a changed string is re-spaced: the indentation between tags is not prose
    return re.sub(r"[ \t]{2,}", " ", text) if changed else text

def strip_page_head(xhtml, header_rx):
    """The running head at the top of a scanned page: the first <p>'s opening 'CAPS CAPS 119 ' or '119 CAPS CAPS '."""
    m = FIRST_P.search(xhtml)
    if not m: return xhtml, 0
    lead = m.group(3)
    for rx in header_rx:
        h = rx.match(lead)
        if h and h.end() < len(lead):
            return xhtml[: m.start(3)] + lead[h.end():] + xhtml[m.end(3):], 1
    return xhtml, 0

def clean_xhtml(xhtml, words, heads, header_rx, counts):
    """Rules over the text between tags only; the markup is never touched."""
    if header_rx:
        xhtml, n = strip_page_head(xhtml, header_rx)
        if n: counts["page_heads"] = counts.get("page_heads", 0) + n
    if not words and not heads: return xhtml
    out, pos = [], 0
    for t in TAG.finditer(xhtml):
        out.append(clean_text(xhtml[pos: t.start()], words, heads, counts)); out.append(t.group(0)); pos = t.end()
    out.append(clean_text(xhtml[pos:], words, heads, counts))
    return "".join(out)

def clean_epub(src, dst, decisions, page_heads=True):
    """src → dst with every XHTML page cleaned; the zip keeps its order and its compression. Returns counts."""
    words, heads = compile_rules(decisions)
    header_rx = _pi().HEADER_RX if page_heads else []
    counts = {}
    src, dst = pathlib.Path(src), pathlib.Path(dst)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.lower().endswith((".xhtml", ".html", ".htm")):
                text = data.decode("utf-8", "replace")
                new = clean_xhtml(text, words, heads, header_rx, counts)
                if new != text: data = new.encode("utf-8"); counts["pages"] = counts.get("pages", 0) + 1
            zout.writestr(info, data, compress_type=zipfile.ZIP_STORED if info.filename == "mimetype" else info.compress_type)
    tmp.replace(dst)
    return counts

def clean_book(book, decisions):
    """The passage file, chunk by chunk, ids untouched. Returns counts."""
    words, heads = compile_rules(decisions)
    counts = {}
    for ch in book.get("chunks", []):
        text = ch.get("text", "")
        new = clean_text(text, words, heads, counts)
        if new != text:
            ch["text"] = new; ch["words"] = len(new.split()); counts["chunks"] = counts.get("chunks", 0) + 1
    return counts

def main():
    a = sys.argv[1:]
    if "--selftest" in a: return selftest()
    if not a or a[0].startswith("-"): print(__doc__); return 2
    slug = a[0]; dry = "--dry-run" in a
    def opt(k): return a[a.index(k) + 1] if k in a and len(a) > a.index(k) + 1 else None
    decisions = load_decisions(slug)
    if not decisions: print(f"epub-clean: no judgements for {slug} in {DECISIONS.relative_to(REPO)}"); return 3
    words, heads = compile_rules(decisions)
    print(f"epub-clean: {slug}: {len(words)} word rule(s), {len(heads)} head rule(s), {sum(1 for d in decisions.values() if d.get('action') == 'keep')} kept")
    src = LIB / f"{slug}.json"
    if src.exists():
        book = json.loads(src.read_text(encoding="utf-8"))
        c = clean_book(book, decisions)
        print(f"epub-clean: passages — {c.get('words', 0)} word change(s), {c.get('heads', 0)} head(s) in {c.get('chunks', 0)} chunk(s)")
        if not dry and c: src.write_text(json.dumps(book, ensure_ascii=False) + "\n", encoding="utf-8")
    epub, out = opt("--epub"), opt("--out")
    if epub and not dry:
        c = clean_epub(epub, out or epub, decisions)
        print(f"epub-clean: EPUB — {c.get('words', 0)} word change(s), {c.get('heads', 0)} judged head(s), {c.get('page_heads', 0)} page head(s) on {c.get('pages', 0)} page(s) → {out or epub}")
        if src.exists():
            pi = _pi(); book = json.loads(src.read_text(encoding="utf-8"))
            e = pi.register_book(pathlib.Path(out or epub), slug, book.get("title", slug), book.get("author", ""), len(book.get("chunks", [])))
            print(f"epub-clean: books.json — {slug} now {e['partial_md5']} (history {len(e.get('md5_history') or [])})")
    return 0

def selftest():
    dec = {"word:achicve": {"kind": "word", "target": "achicve", "action": "fix", "fix": "achieve"},
           "word:proccss": {"kind": "word", "target": "proccss", "action": "fix", "fix": "process"},
           "word:1j": {"kind": "word", "target": "1j", "action": "remove", "fix": ""},
           "word:volga": {"kind": "word", "target": "volga", "action": "keep", "fix": ""},
           "head:Aclassless society": {"kind": "head", "target": "Aclassless society", "action": "remove", "fix": ""}}
    words, heads = compile_rules(dec)
    assert len(words) == 3 and len(heads) == 1
    c = {}
    t = clean_text("Achicve it; they achicve; the proccss 1j of the Volga. Aclassless society 309 rule. A CLASSLESS SOCIETY 310 more.", words, heads, c)
    assert t == "Achieve it; they achieve; the process of the Volga. rule. more.", t
    assert c == {"heads": 2, "words": 4}, c
    assert clean_text("misachicve", words, heads) == "misachicve", "whole words only"
    assert clean_text("a classless society which Marx dreamt of", words, heads) == "a classless society which Marx dreamt of", "a head needs its page number"
    page = '<html><body>\n    <p>THE DREYFUS AFFAIR 119 national misfortune achicve <i>achicve</i> A CLASSLESS SOCIETY 12 x</p></body></html>'
    c = {}
    out = clean_xhtml(page, words, heads, _pi().HEADER_RX, c)
    assert out == '<html><body>\n    <p>national misfortune achieve <i>achieve</i> x</p></body></html>', out
    assert c == {"page_heads": 1, "words": 2, "heads": 1}, c
    # the single-capital head the import used to miss
    out, n = strip_page_head("<p>A CLASSLESS SOCIETY 307 For the propaganda</p>", _pi().HEADER_RX)
    assert n == 1 and out == "<p>For the propaganda</p>", out
    out, n = strip_page_head("<p>CHAPTER TEN: A Classless Society 1! The Masses</p>", _pi().HEADER_RX)
    assert n == 0, out
    book = {"chunks": [{"id": "B001", "text": "they achicve", "words": 2}, {"id": "B002", "text": "fine", "words": 1}]}
    assert clean_book(book, dec) == {"words": 1, "chunks": 1} and book["chunks"][0]["text"] == "they achieve" and book["chunks"][0]["id"] == "B001"
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td); src = td / "b.epub"
        with zipfile.ZipFile(src, "w") as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("EPUB/page_1.html", page, compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("EPUB/style.css", "p{}", compress_type=zipfile.ZIP_DEFLATED)
        c = clean_epub(src, td / "c.epub", dec)
        with zipfile.ZipFile(td / "c.epub") as z:
            assert z.namelist()[0] == "mimetype" and z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
            assert "achieve" in z.read("EPUB/page_1.html").decode() and z.read("EPUB/style.css") == b"p{}"
        assert c["pages"] == 1 and c["page_heads"] == 1, c
    print("epub-clean selftest: OK")

if __name__ == "__main__":
    sys.exit(main())
