#!/usr/bin/env python3
"""KOReader (phone) → repo: vocabulary lookups, reading minutes, and the position in the book.

    python3 scripts/koreader-pull.py                # Mac: reads the Drive mount; cloud: kosync only
    python3 scripts/koreader-pull.py --dir <folder> # a folder holding vocabulary_builder.sqlite3 / statistics.sqlite3
    python3 scripts/koreader-pull.py --check        # verify the kosync credentials and exit
    python3 scripts/koreader-pull.py --selftest

The reading sensor, the way gpodder is the listening sensor:

  phone   KOReader keeps its data in <storage>/koreader/settings/ — vocabulary_builder.sqlite3
          (words added from dictionary lookups, with the sentence context) and statistics.sqlite3
          (seconds per page, per book, with the book's partial-MD5). An Autosync folder pair uploads
          that folder to Drive: My Drive/EnglishPractice/koreader/. KOReader's progress sync plugin
          (kosync, sync.koreader.rocks) publishes the position in each book.
  Mac     the nightly job reads the Drive mount (sources() below) → logs/reading/*.json → git.
  cloud   with KOSYNC_USER + KOSYNC_PASS set (environment variables, never git), the Routine pulls
          the position; with --dir it also folds sqlite files fetched from Drive.

Outputs (all merged, idempotent):
  logs/reading/vocab.json      unified lookup store — same entries as the Kindle bridge (kindle-vocab.py),
                               ids "ko:<word>"; carded flags are preserved across pulls
  logs/reading/daily.json      {date: {min, pages, books}} from statistics (Europe/London dates)
  logs/reading/progress.json   {slug: {title, percentage, passage, page, total_pages, device, timestamp, source}}
  logs/reading/books.json      book registry (slug, title, partial_md5, filename_md5, passages) — written by
                               passage-import.py; books met only in statistics are appended with their md5

Reading minutes are load, the lookups are harvest, the position is a pointer: none of it is a score,
nothing feeds tracking.tsv. Credentials never go into git, the Hub store, or chat.
"""
import datetime as dt, hashlib, json, math, os, pathlib, sqlite3, sys, tempfile, urllib.error, urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
RDIR = REPO / "logs" / "reading"
VOCAB, DAILY, PROGRESS, BOOKS = RDIR / "vocab.json", RDIR / "daily.json", RDIR / "progress.json", RDIR / "books.json"
LEGACY_VOCAB = REPO / "logs" / "kindle-vocab.json"
KOSYNC_SERVER = os.environ.get("KOSYNC_SERVER", "https://sync.koreader.rocks")
UA = "english-runbook/1.0"

def load(p, default):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError): return default

def dump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)

def local_date(ts):
    """KOReader stores epoch seconds; the day is the user's day (Europe/London), not UTC's."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/London")
    except Exception:
        tz = dt.timezone.utc
    return dt.datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d")

def partial_md5(path):
    """KOReader's document id (util.partialMD5): 1 KiB samples at 0, 1K, 4K, 16K … 1G, stop at EOF."""
    m = hashlib.md5()
    with open(path, "rb") as f:
        for i in range(-1, 11):
            f.seek(0 if i == -1 else 1024 << (2 * i))
            s = f.read(1024)
            if not s: break
            m.update(s)
    return m.hexdigest()

def sources():
    """Folders that may hold the synced KOReader settings (first match wins)."""
    out = []
    if os.environ.get("KOREADER_DIR"): out.append(pathlib.Path(os.environ["KOREADER_DIR"]))
    home = pathlib.Path.home()
    for mount in sorted((home / "Library/CloudStorage").glob("GoogleDrive-*")):
        base = mount / "My Drive" / "EnglishPractice" / "koreader"
        out += [base, base / "settings"]
    return out

def find_dir(explicit=None):
    for d in ([pathlib.Path(explicit)] if explicit else []) + sources():
        if (d / "vocabulary_builder.sqlite3").exists() or (d / "statistics.sqlite3").exists():
            return d
    return None

def ro(path):
    # copy first: the Drive client or KOReader may be writing; a read-only URI still takes a shared lock
    tmp = pathlib.Path(tempfile.mkdtemp()) / path.name
    tmp.write_bytes(path.read_bytes())
    return sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)

def columns(con, table):
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]

def read_vocab(con):
    """Rows of KOReader's vocabulary builder, both schemas (book_title column, or title_id → title table)."""
    cols = columns(con, "vocabulary")
    if not cols: return []
    if "title_id" in cols:
        q = ("SELECT v.word, t.name, v.create_time, v.review_count, v.streak_count, v.prev_context, v.next_context, v.highlight "
             "FROM vocabulary v LEFT JOIN title t ON t.id = v.title_id ORDER BY v.create_time")
    else:
        q = ("SELECT word, book_title, create_time, review_count, streak_count, prev_context, next_context, "
             + ("highlight" if "highlight" in cols else "NULL") + " FROM vocabulary ORDER BY create_time")
    out = []
    for word, book, ct, rc, sc, prev, nxt, hl in con.execute(q):
        usage = " ".join(x.strip() for x in ((prev or ""), word, (nxt or "")) if x and x.strip())
        out.append({"id": f"ko:{word}", "word": word, "stem": word, "usage": usage[:300], "book": book or "unknown",
                    "ts": int(ct or 0) * 1000, "source": "koreader", "review_count": int(rc or 0), "streak": int(sc or 0),
                    "highlight": (hl or "")[:300], "carded": False})
    return out

def read_stats(con):
    """Per-day minutes/pages from statistics.sqlite3, plus per-book position and md5."""
    cols = columns(con, "page_stat_data")
    if cols:
        q = "SELECT id_book, page, start_time, duration, total_pages FROM page_stat_data ORDER BY start_time"
    elif columns(con, "page_stat"):
        q = "SELECT id_book, page, start_time, period, 0 FROM page_stat ORDER BY start_time"
    else:
        return {}, {}
    books = {r[0]: {"title": r[1], "authors": r[2], "md5": r[3], "pages": r[4]}
             for r in con.execute("SELECT id, title, authors, md5, pages FROM book")}
    days, pos = {}, {}
    for id_book, page, start, dur, total in con.execute(q):
        b = books.get(id_book) or {"title": f"book {id_book}", "md5": None, "pages": 0}
        d = days.setdefault(local_date(int(start)), {"sec": 0, "pages": 0, "books": []})
        d["sec"] += int(dur or 0); d["pages"] += 1
        if b["title"] not in d["books"]: d["books"].append(b["title"])
        p = pos.setdefault(id_book, {"title": b["title"], "md5": b["md5"], "page": 0, "total_pages": 0, "last": 0})
        if int(start) >= p["last"]:
            p.update({"page": int(page or 0), "total_pages": int(total or b["pages"] or 0), "last": int(start)})
    daily = {k: {"min": round(v["sec"] / 60, 1), "pages": v["pages"], "books": v["books"]} for k, v in days.items() if v["sec"] > 0}
    return daily, pos

def passage_for(pct, n_passages):
    if not n_passages or pct is None: return None
    return "B%03d" % min(n_passages, max(1, math.ceil(float(pct) * n_passages)))

def kosync_key(user, password=None, key=None):
    return key or (hashlib.md5(password.encode("utf-8")).hexdigest() if password else None)

def kosync_get(path, user, key, server=KOSYNC_SERVER, timeout=30):
    req = urllib.request.Request(server.rstrip("/") + path, headers={
        "x-auth-user": user, "x-auth-key": key, "accept": "application/vnd.koreader.v1+json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, ValueError, OSError) as e:
        return 0, {"error": str(e)[:200]}

def kosync_progress(books, user, key, server=KOSYNC_SERVER, fetch=kosync_get):
    """Position per registered book from the progress-sync server; tries the binary id, then the filename id."""
    out = {}
    for b in books:
        for doc in (b.get("partial_md5"), b.get("filename_md5")):
            if not doc: continue
            st, r = fetch(f"/syncs/progress/{doc}", user, key, server)
            if st == 200 and r.get("percentage") is not None:
                out[b["slug"]] = {"title": b.get("title"), "percentage": round(float(r["percentage"]), 4),
                                  "passage": passage_for(r["percentage"], b.get("passages")), "device": r.get("device"),
                                  "timestamp": dt.datetime.fromtimestamp(int(r.get("timestamp") or 0), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if r.get("timestamp") else None,
                                  "source": "kosync"}
                break
    return out

def merge_vocab(store, new):
    known = {x["id"]: x for x in store.get("lookups", [])}
    added = 0
    for e in new:
        if e["id"] in known:
            for k in ("review_count", "streak", "highlight"):
                if k in e: known[e["id"]][k] = e[k]
            if not known[e["id"]].get("usage") and e.get("usage"): known[e["id"]]["usage"] = e["usage"]
        else:
            store.setdefault("lookups", []).append(e); known[e["id"]] = e; added += 1
    return added

def fold(vocab_rows, daily_new, positions, kosync, today=None, vocab=None, daily=None, progress=None, books=None):
    """Pure merge of everything read; returns the four documents and a summary."""
    today = today or dt.date.today()
    vocab = vocab if vocab is not None else {"lookups": []}
    daily = daily if daily is not None else {}
    progress = progress if progress is not None else {}
    books = books if books is not None else []
    added = merge_vocab(vocab, vocab_rows)
    if vocab_rows: vocab["synced"] = today.isoformat()
    for k, v in daily_new.items(): daily[k] = v
    by_md5 = {b.get("partial_md5"): b for b in books if b.get("partial_md5")}
    for p in positions.values():
        b = by_md5.get(p.get("md5"))
        if not b:
            if p.get("md5") and not any(x.get("title") == p["title"] for x in books):
                books.append({"slug": None, "title": p["title"], "partial_md5": p["md5"], "passages": None, "seen": "statistics"})
            continue
        pct = (p["page"] / p["total_pages"]) if p.get("total_pages") else None
        cur = progress.get(b["slug"]) or {}
        stamp = dt.datetime.fromtimestamp(p["last"], dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not cur.get("timestamp") or stamp >= cur["timestamp"]:
            progress[b["slug"]] = {"title": b.get("title"), "percentage": round(pct, 4) if pct is not None else None,
                                   "passage": passage_for(pct, b.get("passages")), "page": p["page"], "total_pages": p["total_pages"],
                                   "device": cur.get("device"), "timestamp": stamp, "source": "statistics"}
    for slug, p in kosync.items():
        cur = progress.get(slug) or {}
        if not cur.get("timestamp") or (p.get("timestamp") or "") >= cur["timestamp"]:
            progress[slug] = {**cur, **p}
    return vocab, daily, progress, books, {"vocab_added": added, "days": len(daily_new), "progress": len(progress)}

def selftest():
    con = sqlite3.connect(":memory:")
    con.executescript("""
      CREATE TABLE vocabulary (word TEXT NOT NULL UNIQUE, title_id INTEGER, create_time INTEGER NOT NULL, due_time INTEGER NOT NULL,
        review_time INTEGER, review_count INTEGER NOT NULL DEFAULT 0, prev_context TEXT, next_context TEXT, streak_count INTEGER NOT NULL DEFAULT 0, highlight TEXT);
      CREATE TABLE title (id INTEGER NOT NULL UNIQUE, name TEXT UNIQUE, filter INTEGER NOT NULL DEFAULT 1);
      INSERT INTO title VALUES (1, 'The Origins of Totalitarianism', 1);
      INSERT INTO vocabulary VALUES ('respite', 1, 1788950000, 1789000000, NULL, 2, 'no', 'for the victor', 1, NULL);
      INSERT INTO vocabulary VALUES ('vanquished', 1, 1788900000, 1789000000, NULL, 0, 'no peace treaty for the', 'and no respite', 0, 'the vanquished');
      CREATE TABLE book (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, authors TEXT, notes INTEGER, last_open INTEGER, highlights INTEGER, pages INTEGER,
        series TEXT, language TEXT, md5 TEXT, total_read_time INTEGER, total_read_pages INTEGER);
      CREATE TABLE page_stat_data (id_book INTEGER, page INTEGER NOT NULL DEFAULT 0, start_time INTEGER NOT NULL DEFAULT 0, duration INTEGER NOT NULL DEFAULT 0, total_pages INTEGER NOT NULL DEFAULT 0);
      INSERT INTO book VALUES (1, 'The Origins of Totalitarianism', 'Hannah Arendt', 0, 1788950000, 0, 800, '', 'en', 'bf906459a4b4ca58cf49e66906f9e730', 0, 0);
      INSERT INTO page_stat_data VALUES (1, 95, 1788850000, 40, 800), (1, 96, 1788850040, 50, 800), (1, 97, 1788950000, 30, 800);
    """)
    rows = read_vocab(con)
    assert [r["word"] for r in rows] == ["vanquished", "respite"] and rows[1]["usage"] == "no respite for the victor" and rows[1]["review_count"] == 2, rows
    daily, pos = read_stats(con)
    assert daily == {"2026-09-08": {"min": 1.5, "pages": 2, "books": ["The Origins of Totalitarianism"]}, "2026-09-09": {"min": 0.5, "pages": 1, "books": ["The Origins of Totalitarianism"]}}, daily
    assert pos[1]["page"] == 97 and pos[1]["total_pages"] == 800 and pos[1]["md5"] == "bf906459a4b4ca58cf49e66906f9e730", pos
    # legacy schema
    con2 = sqlite3.connect(":memory:")
    con2.executescript("CREATE TABLE vocabulary (word TEXT, book_title TEXT, create_time INTEGER, due_time INTEGER, review_time INTEGER, review_count INTEGER, prev_context TEXT, next_context TEXT, streak_count INTEGER);"
                       "INSERT INTO vocabulary VALUES ('old', 'Other', 1700000000, 0, 0, 0, NULL, NULL, 0);")
    assert read_vocab(con2)[0]["book"] == "Other" and read_stats(con2) == ({}, {})
    books = [{"slug": "the-origins-of-totalitarianism", "title": "The Origins of Totalitarianism", "partial_md5": "bf906459a4b4ca58cf49e66906f9e730", "filename_md5": "x", "passages": 1433}]
    store = {"lookups": [{"id": "ko:respite", "word": "respite", "usage": "", "book": "The Origins of Totalitarianism", "ts": 1, "carded": True}]}
    vocab, d, prog, bks, s = fold(rows, daily, pos, {}, today=dt.date(2026, 9, 10), vocab=store, books=books)
    assert s["vocab_added"] == 1 and vocab["lookups"][0]["carded"] and vocab["lookups"][0]["usage"] == "no respite for the victor", vocab
    assert prog["the-origins-of-totalitarianism"]["passage"] == "B174" and prog["the-origins-of-totalitarianism"]["source"] == "statistics", prog
    ks = kosync_progress(books, "u", "k", fetch=lambda path, u, k, srv: (200, {"percentage": 0.2, "device": "poco", "timestamp": 1788999999}) if path.endswith("bf906459a4b4ca58cf49e66906f9e730") else (502, {}))
    assert ks["the-origins-of-totalitarianism"]["passage"] == "B287" and ks["the-origins-of-totalitarianism"]["device"] == "poco", ks
    vocab, d, prog, bks, s = fold([], {}, {}, ks, today=dt.date(2026, 9, 10), vocab=vocab, daily=d, progress=prog, books=bks)
    assert prog["the-origins-of-totalitarianism"]["source"] == "kosync" and prog["the-origins-of-totalitarianism"]["page"] == 97, prog   # newer wins, page kept
    assert passage_for(0, 1433) == "B001" and passage_for(1, 1433) == "B1433" and passage_for(0.5, None) is None
    assert kosync_key("u", password="pw") == hashlib.md5(b"pw").hexdigest() and kosync_key("u", key="abc") == "abc"
    # an unregistered book met in statistics is appended to the registry with its md5, never with text
    _, _, _, bks2, _ = fold([], {}, {2: {"title": "Other book", "md5": "deadbeef", "page": 1, "total_pages": 10, "last": 1788950000}}, {}, today=dt.date(2026, 9, 10), books=[])
    assert bks2 == [{"slug": None, "title": "Other book", "partial_md5": "deadbeef", "passages": None, "seen": "statistics"}], bks2
    print("koreader-pull.py selftest: OK")

def main():
    if "--selftest" in sys.argv: return selftest()
    user, key = os.environ.get("KOSYNC_USER"), kosync_key(None, os.environ.get("KOSYNC_PASS"), os.environ.get("KOSYNC_KEY"))
    if "--check" in sys.argv:
        if not (user and key): print("koreader-pull: KOSYNC_USER / KOSYNC_PASS not set"); return 2
        st, r = kosync_get("/users/auth", user, key)
        print(f"kosync {KOSYNC_SERVER}: HTTP {st} {r if st != 200 else 'authorized'}"); return 0 if st == 200 else 1
    explicit = sys.argv[sys.argv.index("--dir") + 1] if "--dir" in sys.argv else None
    d = find_dir(explicit)
    books = load(BOOKS, [])
    vocab_rows, daily_new, positions = [], {}, {}
    if d:
        if (d / "vocabulary_builder.sqlite3").exists():
            con = ro(d / "vocabulary_builder.sqlite3"); vocab_rows = read_vocab(con); con.close()
        if (d / "statistics.sqlite3").exists():
            con = ro(d / "statistics.sqlite3"); daily_new, positions = read_stats(con); con.close()
    ks = kosync_progress(books, user, key) if (user and key and books) else {}
    if not d and not ks:
        print("koreader-pull: no KOReader folder on this machine and no kosync credentials/books — skipped"); return 3
    store = load(VOCAB, None)
    if store is None: store = load(LEGACY_VOCAB, {"lookups": []})   # the Kindle bridge's old file, once
    vocab, daily, progress, books, s = fold(vocab_rows, daily_new, positions, ks, vocab=store,
                                            daily=load(DAILY, {}), progress=load(PROGRESS, {}), books=books)
    dump(VOCAB, vocab); dump(DAILY, daily); dump(PROGRESS, progress); dump(BOOKS, books)
    where = f"folder {d}" if d else "kosync only"
    pos = "; ".join(f"{p.get('title')} {round((p.get('percentage') or 0) * 100)}% ≈ {p.get('passage')} ({p.get('source')})" for p in progress.values()) or "no position"
    print(f"koreader-pull ({where}): +{s['vocab_added']} words ({len(vocab['lookups'])} total), {len(daily_new)} reading days folded, {pos}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
