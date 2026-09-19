#!/usr/bin/env python3
"""Fold the Minimal Pairs app's files (Drive EnglishPractice/pairs, mirrored from the phone's
Documents/MinimalPairs by Autosync) into git, and build the coach's plan for it.

    python3 scripts/pairs-pull.py --dir <folder>      # a folder laid out like Documents/MinimalPairs
    python3 scripts/pairs-pull.py --plan               # (re)build logs/pairs/plan.json from the ledger + sessions
    python3 scripts/pairs-pull.py --selftest

Writes logs/pairs/: sessions/<id>.json (copied once, immutable), state.json, catalog-version.txt,
weekly.tsv (one row per ISO week and contrast: untrained-word accuracy, trials, reaction time,
shortfall) and plan.json (what the coach wants the app to drill; cloud-sync uploads it to Drive).
The app's own scripts do the summarising and the planning: they are taken from the app's public
repository (shallow clone in .cache/minimal-pairs, refreshed when possible) so the two sides
never drift. Misses on 2+ sessions become "Say it (pronunciation)" cards through the normal queue.
Everything here is training telemetry: load and harvest, never a score; nothing feeds tracking.tsv.
"""
import argparse, collections, datetime as dt, importlib.util, json, pathlib, shutil, subprocess, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "logs" / "pairs"
LEDGER = REPO / "logs" / "pronunciation-ledger.json"
APP_REPO = "https://github.com/djaramillo-calle/minimal-pairs"
APP_DIR = REPO / ".cache" / "minimal-pairs"
CARD_MIN_MISSES = 2

def load_json(p, default):
    try: return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError): return default

def app_scripts(app_dir=APP_DIR, log=print):
    """The app's scripts/ folder: shallow-clone or fast-forward its public repo; None when offline and absent."""
    app_dir = pathlib.Path(app_dir)
    try:
        if (app_dir / ".git").exists():
            subprocess.run(["git", "-C", str(app_dir), "pull", "-q", "--ff-only", "--depth", "1"], check=False, capture_output=True, timeout=120)
        else:
            app_dir.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "-q", "--depth", "1", APP_REPO, str(app_dir)], check=True, capture_output=True, timeout=300)
    except (subprocess.SubprocessError, OSError) as e:
        log(f"pairs-pull: app repo not refreshed ({type(e).__name__}); using what is cached")
    return app_dir if (app_dir / "scripts" / "sessions-summary.py").exists() else None

def fold(src, out=OUT, log=print):
    """Copy new session files and the state into logs/pairs/. Returns the list of new session ids."""
    src, out = pathlib.Path(src), pathlib.Path(out)
    (out / "sessions").mkdir(parents=True, exist_ok=True)
    new = []
    for f in sorted((src / "sessions").glob("*.json")) if (src / "sessions").is_dir() else []:
        dest = out / "sessions" / f.name
        if dest.exists(): continue
        s = load_json(f, None)
        if not isinstance(s, dict) or "trials" not in s: log(f"pairs-pull: skipping {f.name} (not a session)"); continue
        shutil.copyfile(f, dest); new.append(f.stem)
    for name in ("state.json", "catalog-version.txt"):
        if (src / name).exists(): shutil.copyfile(src / name, out / name)
    if new: log(f"pairs-pull: {len(new)} new session(s): " + ", ".join(new[-5:]))
    return new

def weekly(out=OUT, app_dir=None, log=print):
    """logs/pairs/weekly.tsv from the app's sessions-summary.py."""
    app_dir = app_dir or app_scripts(log=log)
    if not app_dir: log("pairs-pull: sessions-summary.py unavailable — weekly.tsv not rebuilt"); return None
    r = subprocess.run([sys.executable, str(app_dir / "scripts" / "sessions-summary.py"), str(out / "sessions"), "--out", str(out / "weekly.tsv")], capture_output=True, text=True)
    if r.returncode != 0: log("pairs-pull: sessions-summary failed: " + r.stderr.strip()[-300:]); return None
    return out / "weekly.tsv"

def plan(out=OUT, ledger=LEDGER, app_dir=None, note=None, log=print):
    """logs/pairs/plan.json from the coach's ledger + recent sessions, via the app's plan-from-ledger.py."""
    app_dir = app_dir or app_scripts(log=log)
    if not app_dir: log("pairs-pull: plan-from-ledger.py unavailable — plan not rebuilt"); return None
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(app_dir / "scripts" / "plan-from-ledger.py"), "--catalog", str(app_dir / "data" / "catalog" / "catalog.json"),
           "--sessions", str(out / "sessions"), "--out", str(out / "plan.json")]
    if pathlib.Path(ledger).exists(): cmd += ["--ledger", str(ledger)]
    cmd += ["--note", note or default_note(ledger, out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0: log("pairs-pull: plan-from-ledger failed: " + (r.stderr or r.stdout).strip()[-300:]); return None
    for line in r.stderr.splitlines():
        if "WARNING" in line: log("pairs-pull: " + line.strip())
    return out / "plan.json"

def default_note(ledger_path, out):
    L = load_json(ledger_path, {}); top = sorted(L.get("phonemes", {}).items(), key=lambda kv: -kv[1].get("count", 0))[:2]
    wk = load_json(out / "state.json", {}).get("sessions_completed")
    parts = []
    if top: parts.append("From your reads: " + ", ".join(c for c, _ in top) + ".")
    parts.append("3 minutes, aloud when you answer: say the word you chose." if not wk else f"{wk} sessions done. Say the word you chose, aloud.")
    return " ".join(parts)[:200]

def misses(sessions_dir):
    """word → (contrast, sessions in which it was the target and missed)"""
    m = collections.defaultdict(set); cls = {}
    for f in sorted(pathlib.Path(sessions_dir).glob("*.json")):
        s = load_json(f, {})
        for t in s.get("trials") or []:
            if t.get("correct") is False and t.get("target"):
                m[t["target"]].add(s.get("id") or f.stem); cls[t["target"]] = t.get("contrast", "")
    return {w: (cls[w], len(ids)) for w, ids in m.items()}

def cards_from_misses(out=OUT, min_misses=CARD_MIN_MISSES, queue_path=None, log=print):
    """Words missed as the target on 2+ sessions → production cards (shared queue, dedupe by front)."""
    pr = _load("practice-review")
    carded_path = pathlib.Path(out) / ".carded.json"; carded = set(load_json(carded_path, []))
    cards = []
    for w, (c, n) in sorted(misses(pathlib.Path(out) / "sessions").items(), key=lambda kv: -kv[1][1]):
        if n >= min_misses and w not in carded:
            cards.append({"front": f"Say it (pronunciation, {c}): {w}", "back": f"{w}  — heard wrong {n}× in the pairs drill ({c})"}); carded.add(w)
    n = pr.queue_cards(cards, source="minimal-pairs", kind="drill", tags=["pronunciation", "pairs"], **({"path": queue_path} if queue_path else {})) if cards else 0
    if cards: carded_path.write_text(json.dumps(sorted(carded)) + "\n", encoding="utf-8")
    if n: log(f"pairs-pull: {n} card(s) queued from repeated misses")
    return n

def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def summary_line(out=OUT):
    st = load_json(pathlib.Path(out) / "state.json", {})
    if not st: return "pairs: no sessions yet"
    cs = st.get("contrasts") or {}
    worst = sorted(((v.get("last_untrained_pct"), k) for k, v in cs.items() if v.get("last_untrained_pct") is not None))[:3]
    return (f"pairs: {st.get('sessions_completed', 0)} sessions, streak {st.get('streak_days', 0)}, last {str(st.get('last_session', ''))[:10]}"
            + (" · weakest untrained: " + ", ".join(f"{k} {int(p * 100)}%" for p, k in worst) if worst else ""))

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td); src = td / "phone"; (src / "sessions").mkdir(parents=True)
        def sess(i, day, miss):
            trials = [{"i": 1, "contrast": "th", "pair": "th:think-sink", "target": "think", "other": "sink", "chosen": "sink" if miss else "think", "correct": not miss, "voice": "v", "rt_ms": 900, "replays": 0, "trained": False, "band": "high", "position": "initial"},
                      {"i": 2, "contrast": "s/z", "pair": "s/z:ice-eyes", "target": "ice", "other": "eyes", "chosen": "ice", "correct": True, "voice": "v", "rt_ms": 800, "replays": 0, "trained": True, "band": "high", "position": "final"}]
            return {"version": 1, "id": i, "started": f"{day}T07:00:00Z", "ended": f"{day}T07:03:00Z", "app_version": "0.1.0", "catalog_version": "x", "plan_source": "coach", "plan_written": None, "voices": ["v"],
                    "trials": trials, "summary": {"trials": 2, "correct": 1 if miss else 2, "pct": 0.5 if miss else 1.0, "untrained_trials": 1, "untrained_correct": 0 if miss else 1, "untrained_pct": 0.0 if miss else 1.0, "duration_s": 180, "mean_rt_ms": 850, "untrained_shortfall": 0, "contrasts": {}}}
        (src / "sessions" / "20260910T070000Z.json").write_text(json.dumps(sess("20260910T070000Z", "2026-09-10", True)))
        (src / "sessions" / "20260911T070000Z.json").write_text(json.dumps(sess("20260911T070000Z", "2026-09-11", True)))
        (src / "sessions" / "bad.json").write_text("{not json")
        (src / "state.json").write_text(json.dumps({"version": 1, "sessions_completed": 2, "streak_days": 2, "last_session": "2026-09-11T07:00:00Z", "contrasts": {"th": {"last_untrained_pct": 0.0}, "s/z": {"last_untrained_pct": None}}}))
        out = td / "out"
        assert fold(src, out, log=lambda *a: None) == ["20260910T070000Z", "20260911T070000Z"]
        assert fold(src, out, log=lambda *a: None) == [], "idempotent"
        assert misses(out / "sessions") == {"think": ("th", 2)}
        q = td / "queue.tsv"; q.write_text("id\tcreated\tsource\tkind\tfront\tback\ttags\tstatus\tnote_id\n")
        assert cards_from_misses(out, queue_path=q, log=lambda *a: None) == 1
        assert cards_from_misses(out, queue_path=q, log=lambda *a: None) == 0, "carded once"
        assert "Say it (pronunciation, th): think" in q.read_text()
        assert summary_line(out).startswith("pairs: 2 sessions, streak 2, last 2026-09-11 · weakest untrained: th 0%"), summary_line(out)
        # the app's scripts, when the cached clone exists (network-free): weekly + plan
        app = APP_DIR if (APP_DIR / "scripts" / "sessions-summary.py").exists() else None
        if app:
            assert weekly(out, app_dir=app, log=lambda *a: None) and "th" in (out / "weekly.tsv").read_text()
            led = td / "ledger.json"; led.write_text(json.dumps({"phonemes": {"th": {"count": 5, "words": {}}}}))
            p = plan(out, ledger=led, app_dir=app, log=lambda *a: None); P = json.loads(p.read_text())
            assert P["weights"]["th"] == 1.0 and P["version"] == 1 and "From your reads: th" in P["note"], P
    print("pairs-pull.py selftest: OK")

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", type=pathlib.Path, help="a folder laid out like Documents/MinimalPairs (sessions/, state.json)")
    ap.add_argument("--plan", action="store_true", help="rebuild logs/pairs/plan.json from the ledger and the sessions")
    ap.add_argument("--note", help="override the plan note")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return selftest()
    if not a.dir and not a.plan: ap.error("--dir or --plan")
    app = app_scripts()
    if a.dir:
        new = fold(a.dir)
        if new or not (OUT / "weekly.tsv").exists(): weekly(app_dir=app)
        cards_from_misses()
    if a.plan or (a.dir and new):
        p = plan(app_dir=app, note=a.note)
        if p: print(f"pairs-pull: plan → {p}")
    print(summary_line())
    return 0

if __name__ == "__main__":
    sys.exit(main())
