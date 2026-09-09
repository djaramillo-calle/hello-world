#!/usr/bin/env python3
"""Anki stats WITHOUT AnkiConnect: read the collection SQLite directly.

    python3 scripts/anki-revlog.py                 # auto-locate the profile collection
    python3 scripts/anki-revlog.py /path/collection.anki2
    python3 scripts/anki-revlog.py --selftest

Writes logs/anki-stats.json in the same shape as scripts/anki-stats.py
(deck-scoped counts, reviews per day, leech candidates), so the weekly
rollup and the Friday review read either source unchanged.

Only safe when desktop Anki is NOT running: Anki opens the collection with
locking_mode=exclusive + WAL, so a second reader gets SQLITE_BUSY, and a
plain copy of the main file loses uncheckpointed WAL data. The script refuses
to run while an Anki process exists; coach-sync.sh --unattended handles the
open/closed decision (AnkiConnect when open, this when closed).
"""
import datetime as dt, json, os, pathlib, shutil, sqlite3, subprocess, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "logs" / "anki-stats.json"
DECK = "English Runbook"
ROLLOVER_H = 4          # Anki's day starts at 04:00 local by default
DAYS = 60

def anki_running():
    try:
        return subprocess.run(["pgrep", "-x", "Anki"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False

def find_collection():
    base = pathlib.Path.home() / "Library/Application Support/Anki2"
    cands = sorted(base.glob("*/collection.anki2"), key=lambda p: p.stat().st_mtime, reverse=True)
    cands = [c for c in cands if c.parent.name not in ("addons21",)]
    return cands[0] if cands else None

def deck_ids(con, deck):
    """Deck id(s) for `deck` and its subdecks (schema 11: JSON in col.decks; 15+: decks table)."""
    ids = []
    tabs = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    if "decks" in tabs:
        for did, name in con.execute("select id, name from decks"):
            n = name.replace("\x1f", "::")
            if n == deck or n.startswith(deck + "::"):
                ids.append(did)
    else:
        raw = con.execute("select decks from col").fetchone()[0]
        for did, d in json.loads(raw).items():
            if d["name"] == deck or d["name"].startswith(deck + "::"):
                ids.append(int(did))
    return ids

def stats(db_path, deck=DECK, today=None, rollover_h=ROLLOVER_H):
    with tempfile.TemporaryDirectory() as td:
        # read a snapshot (main file + WAL sibling if one was left behind)
        snap = pathlib.Path(td) / "collection.anki2"
        shutil.copy2(db_path, snap)
        wal = pathlib.Path(str(db_path) + "-wal")
        if wal.exists():
            shutil.copy2(wal, str(snap) + "-wal")
        con = sqlite3.connect(f"file:{snap}?mode=ro", uri=True)
        try:
            dids = deck_ids(con, deck)
            if not dids:
                raise SystemExit(f"deck {deck!r} not found")
            q = ",".join(str(d) for d in dids)
            row = con.execute(f"""select count(*), sum(queue=0), sum(queue=2 and ivl<21), sum(queue=2 and ivl>=21),
                                        sum(queue=-1), sum(queue in (1,3)) from cards where did in ({q})""").fetchone()
            counts = {"total": row[0], "new": row[1] or 0, "young": row[2] or 0, "mature": row[3] or 0,
                      "suspended": row[4] or 0, "learning": row[5] or 0}
            today = today or dt.date.today()
            since_ms = int(dt.datetime.combine(today - dt.timedelta(days=DAYS), dt.time(rollover_h)).timestamp() * 1000)
            per_day, secs, ret = {}, {}, {}
            for id_ms, ease, typ, tms in con.execute(f"""select r.id, r.ease, r.type, r.time from revlog r join cards c on c.id=r.cid
                                                        where c.did in ({q}) and r.id>=? and r.type in (0,1,2,3)""", (since_ms,)):
                day = (dt.datetime.fromtimestamp(id_ms / 1000) - dt.timedelta(hours=rollover_h)).date().isoformat()
                per_day[day] = per_day.get(day, 0) + 1
                secs[day] = secs.get(day, 0) + (tms or 0) / 1000
                if typ == 1:
                    a = ret.setdefault(day, [0, 0]); a[0] += 1 if ease > 1 else 0; a[1] += 1
            leeches = [{"cardId": cid, "front": (sfld or "")[:120], "lapses": lapses}
                       for cid, sfld, lapses in con.execute(f"""select c.id, n.sfld, c.lapses from cards c join notes n on n.id=c.nid
                                                                 where c.did in ({q}) and c.lapses>=4 order by c.lapses desc""")]
        finally:
            con.close()
    return {
        "exported": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "deck": deck, "source": "collection.anki2 (direct read)",
        "counts": counts,
        "reviews_per_day_since_last_export": dict(sorted(per_day.items())),
        "review_seconds_per_day": {k: round(v) for k, v in sorted(secs.items())},
        "retention_per_day": {k: round(v[0] / v[1], 3) for k, v in sorted(ret.items()) if v[1]},
        "leech_candidates": leeches,
    }

def make_fixture(path, deck=DECK, day=None):
    """Minimal schema-11-style collection for the selftest (decks JSON in col)."""
    day = day or dt.date(2026, 9, 15)
    con = sqlite3.connect(path)
    con.executescript("""
      create table col (id integer primary key, decks text);
      create table cards (id integer primary key, nid integer, did integer, type integer, queue integer, ivl integer, lapses integer);
      create table notes (id integer primary key, sfld text);
      create table revlog (id integer primary key, cid integer, ease integer, ivl integer, lastIvl integer, factor integer, time integer, type integer);
    """)
    con.execute("insert into col values (1, ?)", (json.dumps({"1": {"name": "Default"}, "2": {"name": deck}, "3": {"name": "Other"}}),))
    con.executemany("insert into notes values (?,?)", [(1, "Say it: the release"), (2, "Phrasal: put off"), (3, "x")])
    con.executemany("insert into cards values (?,?,?,?,?,?,?)", [
        (11, 1, 2, 2, 2, 30, 5), (12, 2, 2, 2, 2, 5, 0), (13, 1, 2, 0, 0, 0, 0), (14, 3, 3, 2, 2, 40, 0)])
    def ms(d, h): return int(dt.datetime.combine(d, dt.time(h)).timestamp() * 1000)
    con.executemany("insert into revlog values (?,?,?,?,?,?,?,?)", [
        (ms(day, 7), 11, 3, 30, 20, 2500, 4000, 1), (ms(day, 7) + 1, 12, 1, 5, 4, 2500, 6000, 1),
        (ms(day, 2), 11, 3, 30, 20, 2500, 4000, 1),           # 02:00 belongs to the previous Anki day
        (ms(day - dt.timedelta(days=1), 21), 12, 3, 5, 4, 2500, 3000, 0),
        (ms(day, 8), 14, 3, 40, 30, 2500, 4000, 1),           # other deck: excluded
    ])
    con.commit(); con.close()

def selftest():
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "collection.anki2"
        day = dt.date(2026, 9, 15)
        make_fixture(p, day=day)
        s = stats(p, today=day)
        assert s["counts"] == {"total": 3, "new": 1, "young": 1, "mature": 1, "suspended": 0, "learning": 0}, s["counts"]
        assert s["reviews_per_day_since_last_export"] == {"2026-09-14": 2, "2026-09-15": 2}, s["reviews_per_day_since_last_export"]
        assert s["retention_per_day"]["2026-09-15"] == 0.5 and s["retention_per_day"]["2026-09-14"] == 1.0, s["retention_per_day"]
        assert s["leech_candidates"] == [{"cardId": 11, "front": "Say it: the release", "lapses": 5}]
    print("anki-revlog.py selftest: OK")

def main():
    if "--selftest" in sys.argv:
        return selftest()
    if anki_running():
        sys.exit("anki-revlog: Anki is running — use scripts/anki-stats.py (AnkiConnect) instead")
    path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else find_collection()
    if not path or not path.exists():
        sys.exit("anki-revlog: collection.anki2 not found (pass the path)")
    s = stats(path)
    OUT.parent.mkdir(exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8"); tmp.replace(OUT)
    last = list(s["reviews_per_day_since_last_export"].items())[-3:]
    print(f"anki-revlog: {s['counts']} | last days: " + ", ".join(f"{k} {v}" for k, v in last) + f" | leeches {len(s['leech_candidates'])}")

if __name__ == "__main__":
    main()
