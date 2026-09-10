#!/usr/bin/env python3
"""The cloud's Anki: queued cards → AnkiWeb, review stats ← AnkiWeb, with the official Anki library.

    python3 scripts/anki-cloud.py               # needs ANKIWEB_USER + ANKIWEB_PASS (environment variables, never git)
    python3 scripts/anki-cloud.py --dry-run     # sync + report, add nothing
    python3 scripts/anki-cloud.py --check       # log in and report the collection's sync state, change nothing
    python3 scripts/anki-cloud.py --selftest

Why: desktop Anki + AnkiConnect live on the Mac; a cloud session cannot reach them. This script is the
same code path the desktop app uses to talk to AnkiWeb (the `anki` library's sync backend), run with the
user's own account, so cards queued anywhere (recordings, Talk sessions, dictionary lookups) reach
AnkiWeb — and AnkiDroid/desktop at their next sync — without the Mac. Chosen by the user on 2026-09-10
(credentials in the CCR environment only).

Each run starts from an EMPTY collection in a temporary folder, downloads the account's collection from
AnkiWeb, adds notes under the 25-new-per-rolling-week cap (dedupe by front, deck "English Runbook",
Basic model), performs a normal sync (incremental upload), exports logs/anki-stats.json from the
downloaded collection, and marks the queue rows added. It NEVER performs a full upload: if AnkiWeb asks
for one, the run aborts and leaves the queue untouched — the desktop decides such conflicts.

Bootstraps its own venv (.venv-anki, gitignored) with the `anki` package on first use.
"""
import datetime as dt, importlib.util, json, os, pathlib, subprocess, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
VENV = REPO / ".venv-anki"
DECK, MODEL, CAP = "English Runbook", "Basic", 25
STATS_OUT = REPO / "logs" / "anki-stats.json"

def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def ensure_anki():
    """Re-exec under .venv-anki (creating it with `pip install anki`) when the library is missing."""
    try:
        import anki  # noqa: F401
        return
    except ImportError:
        pass
    py = VENV / "bin" / "python"
    if os.environ.get("ANKI_CLOUD_REEXEC"):
        sys.exit("anki-cloud: the anki library is still missing inside .venv-anki (delete the folder and run again)")
    if not (VENV / "pyvenv.cfg").exists():
        print("anki-cloud: creating .venv-anki and installing the anki library (one-off, ~1 min)…", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    if not (VENV / "lib").exists() or not any(VENV.glob("lib/python*/site-packages/anki")):
        subprocess.run([str(py), "-m", "pip", "install", "-q", "anki"], check=True)
    os.environ["ANKI_CLOUD_REEXEC"] = "1"
    os.execv(str(py), [str(py)] + sys.argv)

def tls_env():
    """The cloud's outbound proxy signs with its own CA; the Rust backend reads SSL_CERT_FILE."""
    ca = "/root/.ccr/ca-bundle.crt"
    if os.environ.get("HTTPS_PROXY") and not os.environ.get("SSL_CERT_FILE") and pathlib.Path(ca).exists():
        os.environ["SSL_CERT_FILE"] = ca

def open_from_ankiweb(workdir, user, password, log=print):
    """Fresh collection ← AnkiWeb. Returns (col, auth). Aborts rather than ever uploading a full collection."""
    from anki.collection import Collection
    from anki import sync_pb2
    R = sync_pb2.SyncCollectionResponse
    col = Collection(str(pathlib.Path(workdir) / "collection.anki2"))
    auth = col.sync_login(user, password, None)
    out = col.sync_collection(auth, False)
    if out.new_endpoint: auth.endpoint = out.new_endpoint
    log(f"anki-cloud: first sync from an empty collection → required={R.ChangesRequired.Name(out.required)}"
        + (f" · server says: {out.server_message}" if out.server_message else ""))
    if out.required in (R.FULL_SYNC, R.FULL_DOWNLOAD):
        log("anki-cloud: downloading the collection from AnkiWeb")
        col.close_for_full_sync()
        col.full_upload_or_download(auth=auth, server_usn=out.server_media_usn, upload=False)
        col.reopen(after_full_sync=True)
    elif out.required == R.FULL_UPLOAD:
        col.close(); raise SystemExit("anki-cloud: AnkiWeb asks for a FULL UPLOAD from an empty collection — refusing; sync the desktop first")
    return col, auth

def deck_fronts(col, deck=DECK):
    did = col.decks.id_for_name(deck)
    if not did: return None, set()
    fronts = set()
    for nid in col.find_notes(f'"deck:{deck}"'):
        fronts.add(col.get_note(nid)["Front"].strip().lower())
    return did, fronts

def add_cards(col, rows, now=None, dry=False, log=print):
    """Queued rows → notes, under the cap and dedupe rules of anki-push-cards.py. Returns (added rows, room)."""
    apc = _load("anki-push-cards")
    now = now or dt.datetime.now(dt.timezone.utc)
    did, fronts = deck_fronts(col)
    used = max(apc.added_last_week(rows, now), len(col.find_notes(f'"deck:{DECK}" added:7')) if did else 0)
    room = max(0, CAP - used)
    todo = [r for r in rows if r.get("status") == "queued"]
    if not todo or dry: return [], room
    if not did: did = col.decks.id(DECK)
    model = col.models.by_name(MODEL) or col.models.all()[0]
    added = []
    for r in todo:
        if len(added) >= room: break
        if r["front"].strip().lower() in fronts:
            r["status"] = "skipped"; continue
        n = col.new_note(model); n["Front"] = r["front"]; n["Back"] = r["back"]; n.tags = (r.get("tags") or "auto").split()
        col.add_note(n, did); fronts.add(r["front"].strip().lower())
        r["_nid"] = n.id; added.append(r)
    return added, room

def commit_added(added, now):
    for r in added:
        r["status"] = "added"; r["note_id"] = str(r.pop("_nid")); r["added_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

def export_stats(col_path, today=None):
    rv = _load("anki-revlog")
    s = rv.stats(col_path, DECK, today)
    s["source"] = "ankiweb (cloud, anki-cloud.py)"
    STATS_OUT.parent.mkdir(exist_ok=True)
    tmp = STATS_OUT.with_suffix(".json.tmp"); tmp.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8"); tmp.replace(STATS_OUT)
    return s

def run(user, password, dry=False, check=False, log=print):
    from anki import sync_pb2
    R = sync_pb2.SyncCollectionResponse
    pr = _load("practice-review")
    rows = pr.load_queue()
    with tempfile.TemporaryDirectory() as td:
        col, auth = open_from_ankiweb(td, user, password, log)
        path = col.path
        try:
            did, fronts = deck_fronts(col)
            week = len(col.find_notes(f'"deck:{DECK}" added:7')) if did else 0
            total = len(col.find_notes("")); decks = [d.name for d in col.decks.all_names_and_ids()]
            log(f"anki-cloud: collection state — {total} notes in {len(decks)} decks {decks[:8]}; deck {DECK!r} {'found' if did else 'MISSING'}, {len(fronts)} notes, {week} added in the last 7 days")
            if total == 0:
                log("anki-cloud: the AnkiWeb account holds NO collection yet (never synced from a desktop/AnkiDroid) — sync once from the desktop with this account first; this script never uploads a full collection")
                if not check: return 4
            if check: return 0
            now = dt.datetime.now(dt.timezone.utc)
            added, room = add_cards(col, rows, now, dry, log)
            if added:
                out = col.sync_collection(auth, False)
                if out.required not in (R.NO_CHANGES, R.NORMAL_SYNC):
                    for r in added: r.pop("_nid", None)
                    raise SystemExit(f"anki-cloud: after adding {len(added)} notes AnkiWeb answered required={R.ChangesRequired.Name(out.required)} — not uploaded, queue left as is")
                commit_added(added, now)
                pr.save_queue(rows)
            log(f"anki-cloud: {'would add' if dry else 'added'} {len(added)} (weekly room {room}); queued left {sum(1 for r in rows if r.get('status') == 'queued')}")
        finally:
            col.close()
        s = export_stats(path)
        log(f"anki-cloud: stats exported → {STATS_OUT.relative_to(REPO)} ({s['counts']['total']} cards, {sum(s['reviews_per_day_since_last_export'].values())} reviews in 60 days)")
    return 0

def selftest():
    import re
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    calls = re.findall(r"full_upload_or_download\((.*?)\)", src)
    assert calls and all("upload=False" in c for c in calls), "this script must never full-upload a collection: %r" % calls
    ensure_anki()
    from anki.collection import Collection
    with tempfile.TemporaryDirectory() as td:
        col = Collection(str(pathlib.Path(td) / "collection.anki2"))
        rows = [{"id": "c1", "created": "2026-09-10T00:00:00Z", "front": "Say it: a", "back": "a", "tags": "auto", "status": "queued"},
                {"id": "c2", "created": "2026-09-10T00:00:00Z", "front": "Say it: a", "back": "dup", "tags": "auto", "status": "queued"},
                {"id": "c3", "created": "2026-09-10T00:00:00Z", "front": "Say it: b", "back": "b", "tags": "auto", "status": "queued"}]
        now = dt.datetime(2026, 9, 10, 12, tzinfo=dt.timezone.utc)
        added, room = add_cards(col, rows, now, dry=True, log=lambda *a: None)
        assert added == [] and room == 25 and all(r["status"] == "queued" for r in rows)
        added, room = add_cards(col, rows, now, log=lambda *a: None)
        assert [r["id"] for r in added] == ["c1", "c3"] and rows[1]["status"] == "skipped", rows
        commit_added(added, now)
        assert rows[0]["status"] == "added" and rows[0]["note_id"].isdigit() and rows[0]["added_at"] == "2026-09-10T12:00:00Z"
        assert len(col.find_notes(f'"deck:{DECK}"')) == 2 and col.get_note(int(rows[0]["note_id"]))["Front"] == "Say it: a"
        old = [{"id": f"o{i}", "created": "2026-09-09T00:00:00Z", "added_at": "2026-09-09T00:00:00Z", "front": f"old {i}", "back": "x", "status": "added"} for i in range(23)]
        rows2 = old + [{"id": "c4", "created": "2026-09-10T00:00:00Z", "front": "Say it: c", "back": "c", "tags": "auto", "status": "queued"}]
        added, room = add_cards(col, rows2, now, log=lambda *a: None)
        assert room == 2 and [r["id"] for r in added] == ["c4"], "the cap counts max(queue rows added this week, deck notes added this week) = 23 → room 2: %r" % room
        rows3 = [dict(r) for r in old] + [{"id": f"q{i}", "created": "2026-09-10T00:00:00Z", "front": f"Say it: q{i}", "back": "q", "tags": "auto", "status": "queued"} for i in range(4)]
        added, room = add_cards(col, rows3, now, log=lambda *a: None)
        assert room == 2 and len(added) == 2 and rows3[-1]["status"] == "queued", "only the room is filled; the rest stays queued: %r" % [r["status"] for r in rows3[-4:]]
        col.close()
        rv = _load("anki-revlog"); s = rv.stats(pathlib.Path(td) / "collection.anki2", DECK, dt.date(2026, 9, 10))
        assert s["counts"]["total"] == 5 and s["counts"]["new"] == 5, s["counts"]   # a, b, c4, q0, q1
    print("anki-cloud.py selftest: OK")

def main():
    if "--selftest" in sys.argv: return selftest()
    user, password = os.environ.get("ANKIWEB_USER"), os.environ.get("ANKIWEB_PASS")
    if not user or not password:
        print("anki-cloud: ANKIWEB_USER / ANKIWEB_PASS not set — nothing to do (the Mac's nightly job pushes cards instead)"); return 3
    ensure_anki(); tls_env()
    return run(user, password, dry="--dry-run" in sys.argv, check="--check" in sys.argv)

if __name__ == "__main__":
    sys.exit(main())
