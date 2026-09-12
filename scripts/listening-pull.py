#!/usr/bin/env python3
"""Listening telemetry: pull episode play actions from a gpodder-protocol
sync server (gpodder.net or self-hosted oPodSync) that AntennaPod on the
phone reports to, and bucket attended minutes per local day.

    GPODDER_USER=... GPODDER_PASS=... python3 scripts/listening-pull.py
    GPODDER_BASE=https://my.opodsync.example ...   # default https://gpodder.net
    python3 scripts/listening-pull.py --creds <json>   # {user, pass, base} — cloud Routines dump it from the Hub store
    python3 scripts/listening-pull.py --selftest

Outputs:
  logs/listening/actions.json   raw play actions (append-only, deduplicated)
  logs/listening/daily.json     {date: {"min": attended minutes, "episodes": n}}
  logs/listening/state.json     {"since": <server timestamp>} so each pull is incremental

AntennaPod enqueues a `play` action on every pause, at playback end and on
every sync while playing, with `started`/`position` seconds. A running session
is re-reported with the same `started` and a growing `position`, so the day's
minutes are the union of each episode's spans (each second counted once), not
the sum. Minutes are LOAD (attended listening), never a score.
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
    """Attended seconds per local day: the UNION of each episode's [started, position] spans.
    AntennaPod re-reports a running session on every sync with the same `started` and a
    growing `position` (31→1631, 31→1879, 31→2352 ...), so summing spans multiplies the
    same minutes; merging overlapping spans per episode counts each second once."""
    spans = {}
    for a in actions:
        if a.get("action") != "play":
            continue
        try:
            t = dt.datetime.fromisoformat(str(a["timestamp"]).replace("Z", ""))
        except (KeyError, ValueError):
            continue
        if t.tzinfo is None: t = t.replace(tzinfo=dt.timezone.utc)   # gpodder timestamps are naive UTC; keep a real offset if one is given
        if zone:
            t = t.astimezone(zone)
        try:
            lo, hi = int(a.get("started") or 0), int(a.get("position") or 0)
        except (TypeError, ValueError):
            continue
        if hi <= lo:
            continue
        spans.setdefault(t.date().isoformat(), {}).setdefault(a.get("episode"), []).append((lo, hi))
    daily = {}
    for day, eps in spans.items():
        sec = 0
        for ranges in eps.values():
            cur_lo = cur_hi = None
            for lo, hi in sorted(ranges):
                if cur_hi is None or lo > cur_hi:
                    if cur_hi is not None: sec += cur_hi - cur_lo
                    cur_lo, cur_hi = lo, hi
                else:
                    cur_hi = max(cur_hi, hi)
            if cur_hi is not None: sec += cur_hi - cur_lo
        daily[day] = {"sec": sec, "episodes": len(eps)}
    return {k: {"min": round(v["sec"] / 60), "episodes": v["episodes"]} for k, v in sorted(daily.items())}

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
        # AntennaPod re-reports one running session with the same start and a growing position: count it once
        {"podcast": "p", "episode": "e3", "device": "poco", "action": "play", "timestamp": "2026-09-11T16:31:00", "started": 31, "position": 1631, "total": 2868},
        {"podcast": "p", "episode": "e3", "device": "poco", "action": "play", "timestamp": "2026-09-11T16:35:19", "started": 31, "position": 1879, "total": 2868},
        {"podcast": "p", "episode": "e3", "device": "poco", "action": "play", "timestamp": "2026-09-11T16:43:28", "started": 31, "position": 2495, "total": 2868},
        {"podcast": "p", "episode": "e3", "device": "poco", "action": "play", "timestamp": "2026-09-11T17:20:00", "started": 2600, "position": 2868, "total": 2868},
    ], "timestamp": 1757430000}
    d = bucket(sample["actions"], local_zone())
    assert d["2026-09-08"]["min"] == 25 and d["2026-09-08"]["episodes"] == 1, d
    assert d["2026-09-10"]["min"] == 10, d   # 23:30 UTC on the 9th is 00:30 BST on the 10th
    assert d["2026-09-11"]["min"] == 46 and d["2026-09-11"]["episodes"] == 1, d   # (2495-31)+(2868-2600) = 2732 s ≈ 46′, not 6913 s
    with tempfile.TemporaryDirectory() as td:
        out = pathlib.Path(td)
        assert merge(out, sample["actions"], sample["timestamp"]) == 8
        assert merge(out, sample["actions"], sample["timestamp"]) == 0, "idempotent"
        assert json.loads((out / "state.json").read_text())["since"] == 1757430000
    print("listening-pull.py selftest: OK")

def main():
    if "--selftest" in sys.argv:
        return selftest()
    user, pw = os.environ.get("GPODDER_USER"), os.environ.get("GPODDER_PASS")
    base = os.environ.get("GPODDER_BASE", "https://gpodder.net")
    if "--creds" in sys.argv:   # cloud Routines: a JSON {user, pass, base} dumped from the Hub store (meta/gpodder)
        c = json.loads(pathlib.Path(sys.argv[sys.argv.index("--creds") + 1]).read_text(encoding="utf-8"))
        user, pw, base = c.get("user") or user, c.get("pass") or pw, c.get("base") or base
    if not user or not pw:
        print("listening: GPODDER_USER/GPODDER_PASS not set — skipped"); return
    base = base.rstrip("/")
    sp = OUT / "state.json"
    since = json.loads(sp.read_text()).get("since") if sp.exists() else None
    data = fetch_actions(base, user, pw, since)
    n = merge(OUT, data.get("actions", []), data.get("timestamp"))
    daily = json.loads((OUT / "daily.json").read_text())
    last = list(daily.items())[-3:]
    print(f"listening: {n} new actions; last days: " + ", ".join(f"{k} {v['min']}′" for k, v in last))

if __name__ == "__main__":
    main()
