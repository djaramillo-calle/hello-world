#!/usr/bin/env python3
"""anki-export.py — the AnkiWeb collection's English Runbook deck as one JSON file, for the
migration of the cards into the app (docs in the app repo, docs/CONTRACT.md "Cards").

    python3 scripts/anki-export.py            # download from AnkiWeb (ANKIWEB_USER/PASS) → logs/srs/anki-export.json
    python3 scripts/anki-export.py --selftest

Notes (id, front, back, tags), cards (id, note, type, queue, ivl, due, reps, lapses) and the
whole revlog of the deck (card, ts, ease 1–4, ivl, lastIvl, time ms). Read-only on AnkiWeb: it
uses anki-cloud.py's downloader, which never full-uploads. Run once; the app owns the schedule
from then on and the coach stops pushing cards to Anki."""
import datetime as dt, importlib.util, json, os, pathlib, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "logs" / "srs" / "anki-export.json"

def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def export_collection(col_path, deck="English Runbook"):
    """The deck from an open-able collection file: pure sqlite, no anki library needed."""
    import sqlite3
    con = sqlite3.connect(f"file:{col_path}?mode=ro&immutable=1", uri=True)
    try:
        rv = _load("anki-revlog")
        dids = rv.deck_ids(con, deck)
        if not dids:
            return {"exported": None, "deck": deck, "notes": [], "cards": [], "revlog": []}
        q = ",".join(str(d) for d in dids)
        def cols(table): return {r[1] for r in con.execute(f"pragma table_info({table})")}
        ccols, ncols = cols("cards"), cols("notes")
        pick = lambda have, want, alt="0": want if want in have else alt
        notes, cards, revlog = {}, [], []
        for cid, nid, ctype, queue, ivl, due, reps, lapses in con.execute(
                f"select id, nid, {pick(ccols,'type')}, {pick(ccols,'queue')}, {pick(ccols,'ivl')}, {pick(ccols,'due')}, {pick(ccols,'reps')}, {pick(ccols,'lapses')} from cards where did in ({q}) order by id"):
            cards.append({"id": cid, "note": nid, "type": ctype, "queue": queue, "ivl": ivl, "due": due, "reps": reps, "lapses": lapses})
        nids = ",".join(str(c["note"]) for c in cards) or "0"
        for nid, flds, tags, mod in con.execute(f"select id, {pick(ncols,'flds','sfld')}, {pick(ncols,'tags',chr(39)+chr(39))}, {pick(ncols,'mod')} from notes where id in ({nids})"):
            f = (flds or "").split("\x1f")
            notes[nid] = {"id": nid, "front": f[0] if f else "", "back": f[1] if len(f) > 1 else "", "tags": (tags or "").split(), "modified": mod}
        cids = ",".join(str(c["id"]) for c in cards) or "0"
        for rid, cid, ease, ivl, last_ivl, time_ms, rtype in con.execute(
                f"select id, cid, ease, ivl, lastIvl, time, type from revlog where cid in ({cids}) order by id"):
            revlog.append({"card": cid, "ts": dt.datetime.fromtimestamp(rid / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "ease": ease, "ivl": ivl, "last_ivl": last_ivl, "time_ms": time_ms, "type": rtype})
        return {"exported": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "deck": deck,
                "notes": [notes[c["note"]] for c in cards if c["note"] in notes], "cards": cards, "revlog": revlog}
    finally:
        con.close()

def main():
    if "--selftest" in sys.argv: return selftest()
    ac = _load("anki-cloud")
    ac.ensure_anki(); ac.tls_env()
    user, password = os.environ.get("ANKIWEB_USER"), os.environ.get("ANKIWEB_PASS")
    if not user or not password: print("anki-export: ANKIWEB_USER / ANKIWEB_PASS not set"); return 3
    with tempfile.TemporaryDirectory() as td:
        col, auth, downloaded = ac.open_from_ankiweb(td, user, password)
        path = col.path; col.close()
        data = export_collection(path)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"anki-export: {len(data['notes'])} notes, {len(data['cards'])} cards, {len(data['revlog'])} reviews → {OUT.relative_to(REPO)}")
    return 0

def selftest():
    rv = _load("anki-revlog")
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "collection.anki2"
        rv.make_fixture(p)
        d = export_collection(p)
        assert len(d["cards"]) == 3 and len(d["notes"]) == 3, d["cards"]
        assert all(r["ease"] in (1, 2, 3, 4) for r in d["revlog"]) and d["revlog"], d["revlog"][:2]
        assert d["revlog"] == sorted(d["revlog"], key=lambda r: r["ts"])
        assert export_collection(p, deck="Nope")["cards"] == []
    print("anki-export selftest: OK")

if __name__ == "__main__":
    sys.exit(main())
