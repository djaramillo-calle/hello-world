#!/usr/bin/env python3
"""Listening telemetry: pull episode play actions from a gpodder-protocol
sync server (gpodder.net or self-hosted oPodSync) that AntennaPod on the
phone reports to, and bucket attended minutes per local day.

    GPODDER_USER=... GPODDER_PASS=... python3 scripts/listening-pull.py
    GPODDER_BASE=https://my.opodsync.example ...   # default https://gpodder.net
    python3 scripts/listening-pull.py --selftest

Outputs:
  logs/listening/actions.json   raw play actions (append-only, deduplicated)
  logs/listening/daily.json     {date: {"min": attended minutes, "episodes": n}}
  logs/listening/state.json     {"since": <server timestamp>} so each pull is incremental

AntennaPod enqueues a `play` action on every pause and at playback end with
`started`/`position` seconds, so position-started is time actually played,
not episode length. Minutes are LOAD (attended listening), never a score.
Standard library only (urllib) so it runs on the Mac's stock python3 too.
"""
import base64, datetime as dt, json, os, pathlib, sys, urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "logs" / "listening"
UA = "english-runbook/1.0 (+https://github.com/djaramillo-calle/hello-world)"

def local_zone():
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo("Europe/London")
    except Exception:
        return None

def fetch_actions(base, user, password, since):
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    login = urllib.request.Request(f"{base}/api/2/auth/{user}/login.json", method="POST",
                                   headers={"Authorization": "Basic " + auth, "User-Agent": UA})
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    opener.open(login, timeout=30).read()
    q = f"?aggregated=false" + (f"&since={int(since)}" if since else "")
    req = urllib.request.Request(f"{base}/api/2/episodes/{user}.json{q}",
                                 headers={"Authorization": "Basic " + auth, "User-Agent": UA})
    with opener.open(req, timeout=60) as r:
        return json.loads(r.read())

def action_key(a):
    return f"{a.get('episode')}|{a.get('timestamp')}|{a.get('started')}|{a.get('position')}"

def bucket(actions, zone=None):
    daily = {}
    for a in actions:
        if a.get("action") != "play":
            continue
        try:
            t = dt.datetime.fromisoformat(str(a["timestamp"]).replace("Z", ""))
        except (KeyError, ValueError):
            continue
        t = t.replace(tzinfo=dt.timezone.utc)
        if zone:
            t = t.astimezone(zone)
        try:
            secs = max(0, int(a.get("position") or 0) - int(a.get("started") or 0))
        except (TypeError, ValueError):
            continue
        day = daily.setdefault(t.date().isoformat(), {"sec": 0, "episodes": set()})
        day["sec"] += secs
        day["episodes"].add(a.get("episode"))
    return {k: {"min": round(v["sec"] / 60), "episodes": len(v["episodes"])} for k, v in sorted(daily.items())}

def merge(out, new_actions, server_ts):
    out.mkdir(parents=True, exist_ok=True)
    ap = out / "actions.json"
    have = json.loads(ap.read_text(encoding="utf-8")) if ap.exists() else []
    seen = {action_key(a) for a in have}
    added = [a for a in new_actions if action_key(a) not in seen]
    have.extend(added)
    ap.write_text(json.dumps(have, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "daily.json").write_text(json.dumps(bucket(have, local_zone()), indent=1) + "\n", encoding="utf-8")
    if server_ts:
        (out / "state.json").write_text(json.dumps({"since": server_ts, "pulled": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n", encoding="utf-8")
    return len(added)

def selftest():
    import tempfile
    sample = {"actions": [
        {"podcast": "p", "episode": "e1", "device": "poco", "action": "play", "timestamp": "2026-09-08T12:10:03", "started": 0, "position": 900, "total": 2700},
        {"podcast": "p", "episode": "e1", "device": "poco", "action": "play", "timestamp": "2026-09-08T12:31:00", "started": 900, "position": 1500, "total": 2700},
        {"podcast": "p", "episode": "e2", "device": "poco", "action": "download", "timestamp": "2026-09-08T12:31:00"},
        {"podcast": "p", "episode": "e2", "device": "poco", "action": "play", "timestamp": "2026-09-09T23:30:00", "started": 0, "position": 600, "total": 1800},
    ], "timestamp": 1757430000}
    d = bucket(sample["actions"], local_zone())
    assert d["2026-09-08"]["min"] == 25 and d["2026-09-08"]["episodes"] == 1, d
    assert d["2026-09-10"]["min"] == 10, d   # 23:30 UTC on the 9th is 00:30 BST on the 10th
    with tempfile.TemporaryDirectory() as td:
        out = pathlib.Path(td)
        assert merge(out, sample["actions"], sample["timestamp"]) == 4
        assert merge(out, sample["actions"], sample["timestamp"]) == 0, "idempotent"
        assert json.loads((out / "state.json").read_text())["since"] == 1757430000
    print("listening-pull.py selftest: OK")

def main():
    if "--selftest" in sys.argv:
        return selftest()
    user, pw = os.environ.get("GPODDER_USER"), os.environ.get("GPODDER_PASS")
    if not user or not pw:
        print("listening: GPODDER_USER/GPODDER_PASS not set — skipped"); return
    base = os.environ.get("GPODDER_BASE", "https://gpodder.net").rstrip("/")
    sp = OUT / "state.json"
    since = json.loads(sp.read_text()).get("since") if sp.exists() else None
    data = fetch_actions(base, user, pw, since)
    n = merge(OUT, data.get("actions", []), data.get("timestamp"))
    daily = json.loads((OUT / "daily.json").read_text())
    last = list(daily.items())[-3:]
    print(f"listening: {n} new actions; last days: " + ", ".join(f"{k} {v['min']}′" for k, v in last))

if __name__ == "__main__":
    main()
