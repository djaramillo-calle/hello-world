#!/usr/bin/env python3
"""Kindle Vocabulary Builder -> repo bridge.

Run in a LOCAL session with the Kindle plugged in over USB:

    python3 scripts/kindle-vocab.py /path/to/Kindle/system/vocabulary/vocab.db

Reads the device's lookup history (word + stem + the sentence it appeared
in + book + timestamp), merges new lookups into logs/kindle-vocab.json
(deduplicated by lookup id), and prints the new entries so the session can
turn them into production-format cards per CLAUDE.md.

Schema note: targets the standard Vocabulary Builder schema (WORDS,
LOOKUPS, BOOK_INFO). If a firmware version differs, inspect with
`sqlite3 vocab.db .schema` and adjust the query below.
"""
import json, pathlib, sqlite3, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "logs" / "kindle-vocab.json"

def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    db = sys.argv[1]
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute("""
        SELECT L.id, W.word, W.stem, W.lang, L.usage, B.title, L.timestamp
        FROM LOOKUPS L
        JOIN WORDS W ON W.id = L.word_key
        LEFT JOIN BOOK_INFO B ON B.id = L.book_key
        ORDER BY L.timestamp
    """).fetchall()
    con.close()

    store = {"lookups": []}
    if OUT.exists():
        store = json.loads(OUT.read_text())
    known = {x["id"] for x in store["lookups"]}

    new = []
    for id_, word, stem, lang, usage, title, ts in rows:
        if id_ in known:
            continue
        entry = {
            "id": id_, "word": word, "stem": stem, "lang": lang,
            "usage": (usage or "").strip(), "book": title or "unknown",
            "ts": ts, "carded": False
        }
        store["lookups"].append(entry)
        new.append(entry)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(store, indent=1, ensure_ascii=False))
    print(f"total lookups: {len(store['lookups'])}  |  new this sync: {len(new)}")
    for e in new:
        print(f"  {e['word']}  ({e['book']})")
        if e["usage"]:
            print(f"    “{e['usage']}”")
    if new:
        print("\nNext: turn the best of these into production cards "
              "(front = the usage sentence with the word blanked, said aloud), "
              "mark them carded:true, then commit logs/kindle-vocab.json "
              "with message prefix 'observations:'.")

if __name__ == "__main__":
    main()
