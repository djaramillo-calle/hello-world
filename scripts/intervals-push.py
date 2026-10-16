#!/usr/bin/env python3
"""Push the day's English load into Intervals.icu as custom wellness fields,
so the morning check that already reads running/gym/anthropometry sees the
language training in the same GET.

    INTERVALS_API_KEY=... python3 scripts/intervals-push.py            # last 7 days, idempotent merge
    INTERVALS_API_KEY=... python3 scripts/intervals-push.py --days 30
    python3 scripts/intervals-push.py --dry-run                        # print payloads, no network
    python3 scripts/intervals-push.py --selftest

Sources (all in git): logs/hub/days.json (check-ins + Talk sessions),
logs/listening/daily.json (gpodder pull), logs/anki-stats.json,
logs/practice/*.json, logs/weekly.tsv (floor status on Fridays).

Fields (CustomItem INPUT_FIELD, created once if missing; codes are permanent):
  EngListenMin  EngSrsReviews  EngConversations  EngTalkMin  EngRecordings  EngWpm  EngFillerPct
Load, not ability — none of this is a proficiency score. Custom wellness
fields never touch CTL/ATL. Auth: Basic with username "API_KEY".
"""
import base64, datetime as dt, json, os, pathlib, sys, urllib.request, urllib.error

REPO = pathlib.Path(__file__).resolve().parent.parent
BASE = os.environ.get("INTERVALS_BASE", "https://intervals.icu/api/v1")
ATHLETE = os.environ.get("INTERVALS_ATHLETE_ID", "0")
UA = "english-runbook/1.0"

FIELDS = [
    ("EngListenMin", "English listening (min)", "min", ".0f", "mdi-headphones"),
    ("EngSrsReviews", "English SRS reviews", "", ".0f", "mdi-cards"),
    ("EngConversations", "English conversations", "", ".0f", "mdi-account-voice"),
    ("EngTalkMin", "English AI talk (min)", "min", ".0f", "mdi-robot"),
    ("EngRecordings", "English recordings", "", ".0f", "mdi-microphone"),
    ("EngWpm", "English speech rate (wpm)", "wpm", ".0f", "mdi-speedometer"),
    ("EngFillerPct", "English filler %", "%", ".1f", "mdi-comment-question"),
]

def load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default

def day_payloads(days, repo=REPO):
    hub = load(repo / "logs/hub/days.json", {})
    listening = load(repo / "logs/listening/daily.json", {})
    anki = load(repo / "logs/anki-stats.json", {}).get("reviews_per_day_since_last_export", {}) or {}
    practice = {}
    pdir = repo / "logs/practice"
    if pdir.exists():
        for p in pdir.glob("*.json"):
            if p.name.startswith("."):
                continue
            r = load(p, {})
            d = str(r.get("recorded", ""))[:10]
            if d:
                practice.setdefault(d, []).append(r)
    out = {}
    for d in days:
        k = d.isoformat(); h = hub.get(k, {}); c = h.get("conversations", {}) or {}
        pl = {}
        lm = listening.get(k, {}).get("min") if k in listening else h.get("listen_min")
        if lm is not None: pl["EngListenMin"] = int(lm)
        if k in anki: pl["EngSrsReviews"] = int(anki[k])
        elif h.get("srs") is not None: pl["EngSrsReviews"] = 1 if h["srs"] else 0   # check-in only: presence, not count
        conv = sum(int(c.get(x) or 0) for x in ("ai", "tutor", "circle", "work"))
        if conv or h: pl["EngConversations"] = conv
        if h.get("talk_min"): pl["EngTalkMin"] = int(h["talk_min"])
        recs = practice.get(k, [])
        n_rec = len(recs) or (1 if h.get("recording") else 0)
        if n_rec or h: pl["EngRecordings"] = n_rec
        wp = [float(r["wpm"]) for r in recs if r.get("wpm")]
        if wp: pl["EngWpm"] = round(sum(wp) / len(wp))
        fl = [100.0 * float(r.get("fillers", 0)) / float(r["words"]) for r in recs if r.get("words")]
        if fl: pl["EngFillerPct"] = round(sum(fl) / len(fl), 1)
        if pl:
            out[k] = pl
    return out

def request(method, path, key, body=None):
    auth = base64.b64encode(f"API_KEY:{key}".encode()).decode()
    req = urllib.request.Request(f"{BASE}{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Basic " + auth, "User-Agent": UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else None

def ensure_fields(key):
    have = {ci.get("content", {}).get("code") for ci in request("GET", f"/athlete/{ATHLETE}/custom-item", key) or [] if isinstance(ci, dict)}
    made = []
    for code, name, units, fmt, icon in FIELDS:
        if code in have:
            continue
        request("POST", f"/athlete/{ATHLETE}/custom-item", key, {
            "type": "INPUT_FIELD", "visibility": "PRIVATE", "name": name, "description": "English Runbook load (auto-pushed from git)",
            "content": {"code": code, "name": name, "type": "number", "units": units, "icon": icon, "color": "#2a78d6",
                        "number_format": fmt, "min": 0, "max": None, "options": [], "text_align": "center", "gauge": False}})
        made.append(code)
    return made

def push(key, payloads):
    body = [dict({"id": k}, **v) for k, v in sorted(payloads.items())]
    if not body:
        return 0
    request("PUT", f"/athlete/{ATHLETE}/wellness-bulk", key, body)
    return len(body)

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        repo = pathlib.Path(td)
        (repo / "logs/hub").mkdir(parents=True); (repo / "logs/listening").mkdir(); (repo / "logs/practice").mkdir()
        (repo / "logs/hub/days.json").write_text(json.dumps({"2026-09-15": {"date": "2026-09-15", "listen_min": 15, "srs": True, "conversations": {"ai": 1, "tutor": 1}, "talk_min": 21, "recording": False},
                                                             "2026-09-16": {"date": "2026-09-16", "srs": False, "conversations": {}}}))
        (repo / "logs/listening/daily.json").write_text(json.dumps({"2026-09-15": {"min": 27, "episodes": 2}}))
        (repo / "logs/anki-stats.json").write_text(json.dumps({"reviews_per_day_since_last_export": {"2026-09-15": 44}}))
        (repo / "logs/practice/2026-09-15-eng-432.json").write_text(json.dumps({"recorded": "2026-09-15 18:20", "wpm": 118.4, "words": 240, "fillers": 12}))
        days = [dt.date(2026, 9, 14), dt.date(2026, 9, 15), dt.date(2026, 9, 16)]
        p = day_payloads(days, repo)
        assert "2026-09-14" not in p, p
        assert p["2026-09-15"] == {"EngListenMin": 27, "EngSrsReviews": 44, "EngConversations": 2, "EngTalkMin": 21, "EngRecordings": 1, "EngWpm": 118, "EngFillerPct": 5.0}, p["2026-09-15"]
        assert p["2026-09-16"] == {"EngSrsReviews": 0, "EngConversations": 0, "EngRecordings": 0}, p["2026-09-16"]
    print("intervals-push.py selftest: OK")

def main():
    if "--selftest" in sys.argv:
        return selftest()
    n = 7
    if "--days" in sys.argv:
        n = int(sys.argv[sys.argv.index("--days") + 1])
    today = dt.date.today()
    payloads = day_payloads([today - dt.timedelta(days=i) for i in range(n)])
    if "--dry-run" in sys.argv:
        print(json.dumps(payloads, indent=1)); return
    key = os.environ.get("INTERVALS_API_KEY")
    if not key:
        print("intervals: INTERVALS_API_KEY not set — skipped"); return
    try:
        made = ensure_fields(key)
        if made: print("intervals: created fields " + ", ".join(made))
        print(f"intervals: pushed {push(key, payloads)} day(s)")
    except urllib.error.HTTPError as e:
        sys.exit(f"intervals: HTTP {e.code} {e.reason}: {e.read()[:300]!r}")

if __name__ == "__main__":
    main()
