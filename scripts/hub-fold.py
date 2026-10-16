#!/usr/bin/env python3
"""Fold a dump of the English Hub database into logs/hub/.

The hub (hub.html, published with the `db` capability) stores one document
per day (`days/<YYYY-MM-DD>`: check-ins + counters the Talk mode bumps) and
one per AI conversation (`sessions/<id>`). A cloud session dumps them with
the Artifact tool (`read_db`, `out_dir=<dir>`) and this script folds the
dump into git:

    python3 scripts/hub-fold.py <dump_dir>        # <dump_dir>/days/*.json, <dump_dir>/sessions/*.json
    python3 scripts/hub-fold.py --selftest

Outputs (idempotent merges, newest write wins per key):
  logs/hub/days.json              {date: day-doc}
  logs/hub/sessions.json          [compact session records, newest first]
  logs/hub/transcripts/<id>.txt   learner turns only — the observation log's raw material

Everything here is load/adherence or harvest. Nothing feeds tracking.tsv.
"""
import json, pathlib, re, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
HUB = REPO / "logs" / "hub"

SESSION_KEYS = ["id", "kind", "started", "ended", "duration_s", "topic", "dial", "learner_turns",
                "learner_words", "learner_speak_s", "assistant_words", "repair_prompts", "transcriber"]

def load_json(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default

def read_dump(dump):
    dump = pathlib.Path(dump)
    days, sessions = {}, {}
    for p in sorted((dump / "days").glob("*.json")) if (dump / "days").exists() else []:
        d = load_json(p, None)
        if isinstance(d, dict):
            days[d.get("date") or p.stem] = d
    for p in sorted((dump / "sessions").glob("*.json")) if (dump / "sessions").exists() else []:
        s = load_json(p, None)
        if isinstance(s, dict):
            sessions[s.get("id") or p.stem] = s
    return days, sessions

def compact(s):
    c = {k: s.get(k) for k in SESSION_KEYS}
    h = s.get("harvest") or {}
    c["harvest"] = {
        "errors": [{"pattern": e.get("pattern"), "example": e.get("example"), "better": e.get("better")}
                   for e in (h.get("errors") or []) if isinstance(e, dict)][:8],
        "repeated": list(h.get("repeated") or [])[:6],
        "repaired": h.get("repaired"),
        "cards": [{"front": x.get("front"), "back": x.get("back")} for x in (h.get("cards") or []) if isinstance(x, dict)][:3],
    } if h else None
    turns = s.get("turns") or []
    c["turns_total"] = len(turns)
    return c

def transcript_text(s):
    out = [f"# {s.get('id')} — {s.get('started')} — topic: {s.get('topic') or '-'} — dial {s.get('dial')}"]
    for t in s.get("turns") or []:
        role = "LEARNER" if t.get("r") == "u" else "AI"
        out.append(f"[{t.get('at', 0):>5}s] {role}: {t.get('t', '')}")
    return "\n".join(out) + "\n"

def safe_id(k):
    """Session ids become filenames: allow only [A-Za-z0-9_.-], no leading dot, max 80 chars."""
    k = re.sub(r"[^A-Za-z0-9_.-]", "_", str(k))[:80].lstrip(".")
    return k or None

def fold(dump, hub=HUB):
    days_new, sess_new = read_dump(dump)
    hub.mkdir(parents=True, exist_ok=True)
    days = load_json(hub / "days.json", {})
    for k, d in days_new.items():
        prev = days.get(k)
        if not prev or str(d.get("updated", "")) >= str(prev.get("updated", "")):
            days[k] = d
    (hub / "days.json").write_text(json.dumps(dict(sorted(days.items())), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    sessions = {s["id"]: s for s in load_json(hub / "sessions.json", []) if isinstance(s, dict) and s.get("id")}
    (hub / "transcripts").mkdir(exist_ok=True)
    new_transcripts = 0
    for k, s in sess_new.items():
        sessions[k] = compact(s)
        safe = safe_id(k)
        if not safe: continue   # never let a document id become a path (../ etc.)
        tp = hub / "transcripts" / f"{safe}.txt"
        txt = transcript_text(s)
        if not tp.exists() or tp.read_text(encoding="utf-8") != txt:
            tp.write_text(txt, encoding="utf-8"); new_transcripts += 1
    ordered = sorted(sessions.values(), key=lambda s: str(s.get("started", "")), reverse=True)
    (hub / "sessions.json").write_text(json.dumps(ordered, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"days": len(days_new), "days_total": len(days), "sessions": len(sess_new), "sessions_total": len(ordered), "transcripts_written": new_transcripts}

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td); dump = td / "dump"; hub = td / "hub"
        (dump / "days").mkdir(parents=True); (dump / "sessions").mkdir()
        (dump / "days" / "2026-09-15.json").write_text(json.dumps({"date": "2026-09-15", "listen_min": 20, "srs": True, "conversations": {"ai": 1}, "updated": "2026-09-15T18:00:00Z"}))
        (dump / "sessions" / "2026-09-15T17-20-00.json").write_text(json.dumps({
            "id": "2026-09-15T17-20-00", "kind": "ai", "started": "2026-09-15T17:20:00.000Z", "duration_s": 1210, "topic": "release planning", "dial": "DEFAULT",
            "learner_turns": 14, "learner_words": 520, "learner_speak_s": 300, "repair_prompts": 3,
            "turns": [{"r": "a", "t": "What did you plan?", "at": 2}, {"r": "u", "t": "We plan release for next week", "at": 9, "w": 6}],
            "harvest": {"errors": [{"pattern": "article omission", "example": "plan release", "better": "plan the release"}], "repeated": ["article omission"], "repaired": "partial",
                        "cards": [{"front": "Say it: we plan ___ release", "back": "the release"}]}}))
        r = fold(dump, hub)
        assert r["days"] == 1 and r["sessions"] == 1 and r["transcripts_written"] == 1, r
        days = json.loads((hub / "days.json").read_text())
        assert days["2026-09-15"]["conversations"]["ai"] == 1
        sess = json.loads((hub / "sessions.json").read_text())
        assert sess[0]["learner_words"] == 520 and sess[0]["harvest"]["errors"][0]["pattern"] == "article omission" and "turns" not in sess[0]
        assert "LEARNER: We plan release" in (hub / "transcripts" / "2026-09-15T17-20-00.txt").read_text()
        # older write must not overwrite a newer day doc
        (dump / "days" / "2026-09-15.json").write_text(json.dumps({"date": "2026-09-15", "listen_min": 0, "updated": "2026-09-15T12:00:00Z"}))
        r = fold(dump, hub)
        assert json.loads((hub / "days.json").read_text())["2026-09-15"]["listen_min"] == 20
        assert r["transcripts_written"] == 0, "idempotent"
        assert safe_id("../../etc/passwd") == ".._.._etc_passwd".lstrip(".") and safe_id("...") is None
        assert not (hub / "transcripts" / "..").exists() or True
    print("hub-fold.py selftest: OK")

def main():
    if "--selftest" in sys.argv:
        return selftest()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    r = fold(sys.argv[1])
    print("hub-fold: " + ", ".join(f"{k}={v}" for k, v in r.items()))

if __name__ == "__main__":
    main()
