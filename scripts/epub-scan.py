#!/usr/bin/env python3
"""epub-scan.py — the deterministic junk scan of a book (app repo docs/CONTRACT.md, "Cleanup").

    python3 scripts/epub-scan.py <slug>            # library/<slug>.json → library/<slug>.junk.json (+ a summary)
    python3 scripts/epub-scan.py <slug> --show 40  # also print the top candidates
    python3 scripts/epub-scan.py --selftest

A scanned book carries OCR damage ("Apmsesinsy" for a drop-cap ANTISEMITISM). This finds the
words that no dictionary knows and grades them without reading the book: every word of every
passage, lowercased and reduced to its obvious base form, is looked up in WordNet's index (the
same StarDict set the phone holds) and in the 50k frequency list; the misses are the candidates.
Signals, all offline: how often the word occurs, whether it opens a section (decorative type
lives there), whether it is capitalised inside a sentence (a name), the nearest dictionary word by
edit distance, and the section title (a drop-cap misread usually IS the title's word). Tiers:
`certain` / `probable` / `doubtful`. The app's Cleanup screen shows the list; the coach applies
what the user approves (epub-clean.py). No LLM reads the book; at most it sees this list."""
import difflib, json, pathlib, re, struct, subprocess, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
LIB = REPO / "library"
CACHE = REPO / ".cache" / "dict"
WORDNET_IDX = CACHE / "wordnet.idx"
FREQ = REPO / ".cache" / "minimal-pairs" / "data" / "sources" / "en_50k.txt"
DRIVE_IDX = "English Runbook/dict/wordnet/comn_dictd03_wn.idx"
TOKEN = re.compile(r"[A-Za-z][A-Za-z'’-]*")

def stardict_words(idx_path):
    """Every headword of a StarDict .idx (word\\0 + offset + size), lowercased, single words only."""
    data = pathlib.Path(idx_path).read_bytes()
    out, i, n = set(), 0, len(data)
    while i < n:
        j = data.index(b"\0", i)
        w = data[i:j].decode("utf-8", "replace").strip().lower()
        if w and " " not in w: out.add(w)
        i = j + 9
    return out

def freq_words(path):
    out = {}
    try:
        for line in pathlib.Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if parts: out[parts[0].lower()] = len(out)
    except OSError: pass
    return out

def ensure_wordnet(log=print):
    if WORDNET_IDX.exists(): return True
    CACHE.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "drive.py"), "--get", DRIVE_IDX, str(WORDNET_IDX)], capture_output=True, text=True)
    if r.returncode != 0 or not WORDNET_IDX.exists():
        log(f"epub-scan: WordNet index not available ({(r.stderr or r.stdout).strip()[:120]})"); return False
    return True

def base_forms(w):
    """The obvious inflections, so 'temptations', 'assumed' and 'obviously' are not misses."""
    yield w
    if w in IRREGULAR: yield IRREGULAR[w]
    for suf, rep in (("'s", ""), ("’s", ""), ("s'", ""), ("ies", "y"), ("es", ""), ("s", ""), ("ied", "y"), ("ed", ""), ("ed", "e"),
                     ("ing", ""), ("ing", "e"), ("ly", ""), ("ally", "al"), ("bly", "ble"), ("ily", "y"), ("ier", "y"), ("iest", "y"),
                     ("er", ""), ("er", "e"), ("est", ""), ("ness", ""), ("ment", ""), ("ments", ""), ("men", "man"), ("ism", ""), ("isms", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            yield w[: -len(suf)] + rep
    if w.endswith("ing") and len(w) > 5 and w[-4] == w[-5]:   # running → run
        yield w[:-4]
    if w.endswith("ed") and len(w) > 4 and w[-3] == w[-4]:     # stopped → stop
        yield w[:-3]
    if "-" in w:
        for part in w.split("-"):
            if len(part) >= 3: yield part

PREFIXES = ("anti", "non", "pre", "un", "re", "all", "self", "ex", "super", "counter", "pan", "semi", "pseudo", "quasi", "co", "inter", "intra", "sub", "post", "over", "under", "half", "well", "ill", "pro")

IRREGULAR = {"dwelt": "dwell", "spelt": "spell", "learnt": "learn", "dreamt": "dream", "knelt": "kneel", "leapt": "leap", "burnt": "burn",
             "smelt": "smell", "spoilt": "spoil", "spilt": "spill", "lit": "light", "slid": "slide", "strove": "strive", "striven": "strive",
             "trod": "tread", "trodden": "tread", "forsook": "forsake", "forsaken": "forsake", "begot": "beget", "begotten": "beget",
             "clung": "cling", "flung": "fling", "slung": "sling", "wrung": "wring", "swum": "swim", "sprang": "spring", "sprung": "spring",
             "shrank": "shrink", "shrunk": "shrink", "stank": "stink", "stunk": "stink", "bade": "bid", "bidden": "bid", "hewn": "hew",
             "sewn": "sew", "sown": "sow", "strewn": "strew", "shorn": "shear", "slain": "slay", "slew": "slay", "smitten": "smite", "smote": "smite"}

class Lexicon:
    def __init__(self, wordnet, freq):
        self.wordnet, self.freq = wordnet, freq
        self.by_first = {}
        for w in wordnet | set(freq):
            if w.isalpha() and 3 <= len(w) <= 24:
                self.by_first.setdefault(w[0], []).append(w)
                f = ocr_fold(w[0])
                if f != w[0]: self.by_first.setdefault(f, []).append(w)   # carth → earth: c reads as e
    def known(self, w):
        w = w.lower().replace("’", "'")
        if any(f in self.wordnet or f in self.freq for f in base_forms(w)): return True
        # A hyphen the scan dropped: anti-semitic, non-totalitarian, all-embracing, self-evident.
        for pre in PREFIXES:
            if w.startswith(pre) and len(w) - len(pre) >= 3 and any(f in self.wordnet or f in self.freq for f in base_forms(w[len(pre):])): return True
        return False
    def glued_article(self, w):
        """'Aclassless' → 'A classless': a drop-cap article glued to the next word."""
        return len(w) > 4 and w[0] == "a" and self.known(w[1:]) and w[1:] not in ("bout", "gain", "way", "part", "side", "long")
    def nearest(self, w, max_dist=2):
        """(word, kind): kind 'ocr' when the two are the same after the OCR confusions are folded
        (superfiuous → superfluous, bencath → beneath), 'typo' for one plain edit, 'far' for two."""
        w = w.lower()
        pool = [x for x in set(self.by_first.get(w[0], [])) | set(self.by_first.get(ocr_fold(w[0]), [])) if abs(len(x) - len(w)) <= 2]
        best = None
        for cand in difflib.get_close_matches(w, pool, n=8, cutoff=0.7):
            if ocr_fold(cand) == ocr_fold(w): return cand, "ocr"
            d = edit_distance(w, cand)
            # a common word beats a rare one at the same distance (cach → each, not coach)
            rank = self.freq.get(cand, 10**6)
            if d <= max_dist and (best is None or (d, rank) < (best[1], best[2])): best = (cand, d, rank)
        if best is None: return None
        return best[0], ("typo" if best[1] == 1 else "far")

# What a scanner mistakes for what: folding both sides makes a misread equal to its word.
OCR_FOLD = (("rn", "m"), ("li", "h"), ("ii", "u"), ("vv", "w"), ("cl", "d"), ("fl", "f"), ("fi", "f"), ("ff", "f"),
            ("c", "e"), ("l", "i"), ("1", "i"), ("0", "o"), ("j", "i"), ("t", "f"), ("nn", "m"), ("in", "m"), ("y", "v"))

def ocr_fold(w):
    for a, b in OCR_FOLD: w = w.replace(a, b)
    return w

def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

def sentence_of(text, start, end):
    s = max(text.rfind(". ", 0, start), text.rfind("? ", 0, start), text.rfind("! ", 0, start))
    s = 0 if s < 0 else s + 2
    e = min([x for x in (text.find(". ", end), text.find("? ", end), text.find("! ", end)) if x >= 0] or [len(text)])
    return " ".join(text[s:e + 1].split())[:300]

def scan(book, lexicon):
    """The candidates of one book (the library JSON), graded."""
    chunks = book.get("chunks", [])
    chapters = book.get("chapters", [])
    first_ids = {c.get("first") for c in chapters}
    titles = [c.get("title", "") for c in chapters if c.get("title")]
    title_re = re.compile("|".join(re.escape(t) for t in sorted(titles, key=len, reverse=True)), re.I) if titles else None
    counts, occ = {}, {}
    for ch in chunks:
        text = ch.get("text", "")
        tokens = list(TOKEN.finditer(text))
        opening_positions = set()
        if ch.get("id") in first_ids: opening_positions.update(m.start() for m in tokens[:3])
        if title_re:
            for tm in title_re.finditer(text):
                after = [m for m in tokens if m.start() >= tm.end()][:2]
                opening_positions.update(m.start() for m in after)
        for m in tokens:
            raw = m.group(0).strip("'’-")
            if len(raw) < 3 or not re.search(r"[A-Za-z]", raw): continue
            low = raw.lower()
            if lexicon.known(low): continue
            counts[low] = counts.get(low, 0) + 1
            o = occ.setdefault(low, {"forms": {}, "opening": False, "mid_cap": 0, "sentence": None, "chunk": ch.get("id"), "title": None, "heading": [], "quoted": 0})
            o["forms"][raw] = o["forms"].get(raw, 0) + 1
            if m.start() in opening_positions:
                o["opening"] = True
                if title_re:
                    tm = list(title_re.finditer(text[: m.start()]))
                    if tm: o["title"] = tm[-1].group(0)
                # the heading's own words, before the candidate: a drop-cap misread usually IS one of them
                o["heading"] = [t.group(0) for t in tokens if t.start() < m.start()][-3:]
            before = text[max(0, m.start() - 2): m.start()]
            after = text[m.end(): m.end() + 1]
            if before.endswith(("“", '"', "‘", "'")) or after in ("”", '"', "’"): o["quoted"] = o.get("quoted", 0) + 1
            if raw[0].isupper() and before.strip() and not before.strip().endswith((".", "?", "!", ":", "“", '"')): o["mid_cap"] += 1
            if o["sentence"] is None: o["sentence"] = sentence_of(text, m.start(), m.end())
    heads = running_heads(chunks)
    out = []
    for w, n in counts.items():
        o = occ[w]
        near = lexicon.nearest(w)
        fix, kind = None, None
        if lexicon.glued_article(w) and any(f[0] == "A" for f in o["forms"]) and "'" not in w and "’" not in w:
            fix, kind = "a " + w[1:], "glued"
        elif o["opening"]:
            for tw in (TOKEN.findall(o["title"] or "") + o["heading"])[::-1]:
                if tw[0].lower() == w[0] and abs(len(tw) - len(w)) <= 4 and lexicon.known(tw): fix, kind = tw, "heading"; break
        if fix is None and near: fix, kind = near
        odd = bool(re.search(r"[^a-z'’-]", w)) or bool(re.search(r"[bcdfghjklmnpqrstvwxz]{5}", w)) or not re.search(r"[aeiouy]", w)
        name = not o["opening"] and o["mid_cap"] > 0 and o["mid_cap"] >= n / 2
        # A sentence that is mostly unknown words is another language (a bibliography, a quotation):
        # its words are not misreads and must not be "fixed" into English.
        stoks = [t.lower() for t in TOKEN.findall(o["sentence"] or "") if len(t) >= 3]
        others = [t for t in stoks if t != w]
        foreign = len(others) >= 4 and sum(1 for t in others if not lexicon.known(t)) / len(others) > 0.34
        # A word the author set in quotation marks is usually a foreign term or a coinage, not a misread.
        quoted = bool(o["quoted"])
        if kind == "glued": tier = "certain"
        elif o["opening"]: tier = "certain"
        elif foreign: tier, fix, kind = "doubtful", None, "foreign"
        elif name: tier = "doubtful"
        elif quoted: tier = "doubtful"
        elif (kind == "ocr" or odd) and n <= 2: tier = "certain"
        elif n <= 2: tier = "probable"
        else: tier = "doubtful"
        out.append({"word": w, "count": n, "forms": o["forms"], "tier": tier, "fix": fix, "kind": kind, "opening": o["opening"], "name": name,
                    "foreign": foreign, "chunk": o["chunk"], "sentence": o["sentence"]})
    order = {"certain": 0, "probable": 1, "doubtful": 2}
    out.sort(key=lambda r: (order[r["tier"]], -r["count"] if r["tier"] == "doubtful" else r["count"], r["word"]))
    return out, heads

STOP = {"the", "of", "and", "to", "only", "about", "a", "in", "on", "at", "by", "from", "between", "for", "with", "than", "over", "under", "some", "nearly", "almost", "about", "than", "or", "p", "pp", "vol", "no", "chapter", "part", "see", "cf", "ibid"}

HEAD_RE = re.compile(r"((?:[A-Za-z][A-Za-z'’-]*\s+){1,6})(\d{1,3})(?=\s|$)")

def running_heads(chunks, min_count=4):
    """Page headers the scan swept into the text: 'Aclassless society 317', 'Preface xiii'. A phrase of
    up to six words that is followed by a page number, seen at least [min_count] times, is one
    (a real sentence never repeats a phrase before a bare number so often)."""
    counts, sample = {}, {}
    for ch in chunks:
        text = ch.get("text", "")
        for m in HEAD_RE.finditer(text):
            words = m.group(1).split()
            for k in range(1, min(6, len(words)) + 1):
                phrase = " ".join(words[-k:])
                if not any(c.isalpha() for c in phrase): continue
                counts[phrase] = counts.get(phrase, 0) + 1
                sample.setdefault(phrase, " ".join(text[max(0, m.start() - 40): m.end() + 20].split()))
    keep = []
    for phrase, n in counts.items():
        if n < min_count: continue
        # a header is Title Case and more than a stray function word before a figure ("only 10 per cent")
        words = phrase.split()
        if not phrase[0].isupper() or (len(words) == 1 and phrase.lower() in STOP): continue
        # the longest phrase that still reaches the count: 'Aclassless society' rather than 'society'
        longer = any(p != phrase and p.endswith(" " + phrase) and counts[p] >= n * 0.8 for p in counts)
        if longer: continue
        keep.append({"phrase": phrase, "count": n, "sample": sample[phrase]})
    keep.sort(key=lambda r: -r["count"])
    return keep

def main():
    a = sys.argv[1:]
    if "--selftest" in a: return selftest()
    if not a: print(__doc__); return 2
    slug = a[0]
    src = LIB / f"{slug}.json"
    if not src.exists(): print(f"epub-scan: {src} missing (the passage file is built at import)"); return 1
    if not ensure_wordnet(): return 1
    lex = Lexicon(stardict_words(WORDNET_IDX), freq_words(FREQ))
    book = json.loads(src.read_text(encoding="utf-8"))
    rows, heads = scan(book, lex)
    out = LIB / f"{slug}.junk.json"
    out.write_text(json.dumps({"version": 1, "slug": slug, "title": book.get("title"), "candidates": rows, "running_heads": heads}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tiers = {t: sum(1 for r in rows if r["tier"] == t) for t in ("certain", "probable", "doubtful")}
    print(f"epub-scan: {slug}: {len(rows)} candidates — {tiers['certain']} certain, {tiers['probable']} probable, {tiers['doubtful']} doubtful; {len(heads)} running head(s) → {out.relative_to(REPO)}")
    if "--show" in a:
        for h in heads[:12]: print(f"  head     {h['phrase']!r:<40s} ×{h['count']:<4d} {h['sample'][:70]}")
        k = int(a[a.index("--show") + 1]) if len(a) > a.index("--show") + 1 and a[a.index("--show") + 1].isdigit() else 30
        for r in rows[:k]:
            print(f"  {r['tier']:8s} {r['word']:<22s} ×{r['count']:<3d} → {r['fix'] or '?':<18s} {(r['kind'] or ''):<8s}{'[opening] ' if r['opening'] else ''}{'[name] ' if r['name'] else ''}{r['sentence'][:80]}")
    return 0

def selftest():
    lex = Lexicon({"antisemitism", "secular", "ideology", "temptation", "become", "irresistible", "process", "obvious", "stalin", "run", "classless", "society"},
                  {"the": 0, "a": 1, "of": 2, "has": 3, "and": 4, "was": 5, "he": 6, "went": 7, "to": 8})
    assert lex.known("temptations") and lex.known("obviously") and lex.known("running") and not lex.known("apmsesinsy")
    book = {"chapters": [{"title": "Preface To Part One", "first": "B002"}], "chunks": [
        {"id": "B001", "text": "The end of the first preface. Preface to Part One: Antisemitism Apmsesinsy, a secular ideology has become an irresistible temptation."},
        {"id": "B002", "text": "Tcmptation was the word. He went to Volga and Stalin was there. The proccss of the proccss."},
    ]}
    book["chunks"].append({"id": "B003", "text": "Aclassless society 317 Then more text. Aclassless society 318 and again. Aclassless society 319 once more. Aclassless society 320 last."})
    rows, heads = scan(book, lex)
    assert heads and heads[0]["phrase"] == "Aclassless society" and heads[0]["count"] == 4, heads
    rows = {r["word"]: r for r in rows}
    assert rows["aclassless"]["kind"] == "glued" and rows["aclassless"]["fix"] == "a classless", rows["aclassless"]
    assert lex.known("antisecular") and lex.known("nonideology"), "a dropped hyphen is not a misread"
    assert rows["apmsesinsy"]["tier"] == "certain" and rows["apmsesinsy"]["opening"] and rows["apmsesinsy"]["fix"] == "Antisemitism", rows["apmsesinsy"]
    assert rows["tcmptation"]["tier"] == "certain" and rows["tcmptation"]["fix"] == "temptation" and rows["tcmptation"]["kind"] == "ocr", rows["tcmptation"]
    assert ocr_fold("superfiuous") == ocr_fold("superfluous") and ocr_fold("bencath") == ocr_fold("beneath") and ocr_fold("mcustrosity") != ocr_fold("monstrosity")
    assert rows["proccss"]["fix"] == "process" and rows["proccss"]["count"] == 2
    assert rows["volga"]["tier"] == "doubtful" and rows["volga"]["name"], rows["volga"]
    assert "stalin" not in rows, "a dictionary word is never a candidate"
    assert edit_distance("kitten", "sitting") == 3
    print("epub-scan selftest: OK")

if __name__ == "__main__":
    sys.exit(main())
