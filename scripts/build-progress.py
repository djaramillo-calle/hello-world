#!/usr/bin/env python3
"""Build progress.html — the season board (pace chart) — from repo data.

    python3 scripts/build-progress.py            # writes progress.html
    python3 scripts/build-progress.py --selftest

Reads tracking.tsv (time trials), logs/weekly.tsv (load), logs/dial-log.tsv,
logs/anki-stats.json, logs/practice/*.json, observations.md, and the season
constants mirrored from docs/TARGET.md. Embeds the data as JSON in a fixed
page template; the page renders SVG charts client-side. Run at every Friday
review and after every diagnostic; republish the artifact from the output.
"""
import datetime as dt, json, pathlib, re, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "progress.html"

# --- season constants (mirror docs/TARGET.md) -------------------------------
SEASON_WEEKS = 12
TIME_TRIAL_WEEKS = [5, 10, 12]
NOISE = {"wpm": 12, "ctest_pct": 8, "dict_pct": 10, "vocab_size": 1100, "mtld": 8, "evidence_n": 3}
FLOORS = {"wpm": 120, "ctest_pct": 75, "dict_pct": 85, "evidence_n": 10}
METRICS = [  # order = display order
    ("wpm", "Speech rate", "wpm"),
    ("dict_pct", "Dictation", "%"),
    ("ctest_pct", "C-test", "%"),
    ("evidence_n", "Real-world use", "/14"),
    ("vocab_size", "Vocabulary", "families"),
    ("mtld", "Lexical diversity", "MTLD"),
]
TARGET_METRIC = {"DEFAULT": "wpm", "DECODE": "dict_pct", "AUTOMATIZE": "wpm", "RANGE": "mtld", "USE": "evidence_n"}
LOAD_FLOOR = {"conversations": 2, "srs_days": 5, "recordings": 1, "listening_days": 5}

def read_tsv(path):
    if not path.exists(): return []
    lines = [l.rstrip("\n") for l in path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    if not lines: return []
    hdr = lines[0].split("\t")
    return [dict(zip(hdr, l.split("\t"))) for l in lines[1:]]

def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def load_data(repo=REPO, today=None):
    today = today or dt.date.today()
    trials = read_tsv(repo / "tracking.tsv")
    for r in trials:
        for k in list(r):
            if k != "date": r[k] = num(r[k])
    weekly = read_tsv(repo / "logs" / "weekly.tsv")
    dial_rows = read_tsv(repo / "logs" / "dial-log.tsv")
    dial = dial_rows[-1]["dial"] if dial_rows else "DEFAULT"

    anki = None
    p = repo / "logs" / "anki-stats.json"
    if p.exists():
        a = json.loads(p.read_text(encoding="utf-8"))
        anki = {"exported": a.get("exported"), "counts": a.get("counts", {}),
                "reviews": a.get("reviews_per_day_since_last_export", {}) or {}}

    practice = []
    pdir = repo / "logs" / "practice"
    if pdir.exists():
        for f in sorted(pdir.glob("*.json")):
            if f.name.startswith("."): continue
            try:
                r = json.loads(f.read_text(encoding="utf-8"))
                practice.append({"date": str(r.get("recorded", ""))[:10], "wpm": r.get("wpm"),
                                 "fillers": r.get("fillers"), "words": r.get("words"), "source": r.get("source")})
            except Exception:
                pass

    obs = {"PATTERN": 0, "PROMOTED": 0, "WATCHING": 0, "STRENGTH": 0, "RETIRED": 0}
    op = repo / "observations.md"
    if op.exists():
        for m in re.finditer(r"^### (PATTERN|PROMOTED|WATCHING|STRENGTH|RETIRED)\b", op.read_text(encoding="utf-8"), re.M):
            obs[m.group(1)] += 1

    # season clock
    season = {"state": "PRE-SEASON", "week": 0, "baseline": None, "next_trial": None, "days_to_trial": None, "race": None}
    if trials:
        b = dt.date.fromisoformat(trials[0]["date"][:10])
        start = b + dt.timedelta(days=(7 - b.weekday()) % 7 or 7)  # Monday after baseline
        week = (today - start).days // 7 + 1
        season.update({"state": "IN-SEASON" if 1 <= week <= SEASON_WEEKS else ("POST-SEASON" if week > SEASON_WEEKS else "WEEK-0"),
                       "week": max(0, week), "baseline": b.isoformat(), "start": start.isoformat()})
        upcoming = [w for w in TIME_TRIAL_WEEKS if w >= max(week, 1)]
        if upcoming:
            tw = upcoming[0]
            trial_day = start + dt.timedelta(weeks=tw - 1, days=5)  # Saturday of that week
            season.update({"next_trial": trial_day.isoformat(), "next_trial_week": tw,
                           "days_to_trial": (trial_day - today).days})
        season["race"] = (start + dt.timedelta(weeks=SEASON_WEEKS - 1, days=5)).isoformat()

    # targets from baseline
    targets = {}
    if trials:
        b = trials[0]
        for k, _, _ in METRICS:
            if b.get(k) is None: continue
            t = b[k] + NOISE.get(k, 0)
            if k in FLOORS: t = max(t, FLOORS[k])
            targets[k] = round(t)
    primary = TARGET_METRIC.get(dial, "wpm")

    return {"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "today": today.isoformat(), "season": season, "dial": dial, "primary": primary,
            "trials": trials, "targets": targets, "noise": NOISE, "floors": FLOORS,
            "metrics": [{"key": k, "label": l, "unit": u} for k, l, u in METRICS],
            "weekly": weekly, "load_floor": LOAD_FLOOR, "anki": anki, "practice": practice,
            "observations": obs, "season_weeks": SEASON_WEEKS, "trial_weeks": TIME_TRIAL_WEEKS}

TEMPLATE = r"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>English Season Board</title>
<style>
  :root {
    color-scheme: light;
    --ground: #F1F2EF; --surface-1: #FBFBF9; --panel-2: #E7E9E4;
    --text-primary: #16191A; --text-secondary: #57605C; --text-muted: #6C7570;
    --grid: #E1E0D9; --axis: #C3C2B7; --border: rgba(11,11,11,0.10);
    --series-1: #2a78d6; --series-1-wash: rgba(42,120,214,0.10);
    --seq-100: #cde2fb; --seq-250: #86b6ef; --seq-400: #3987e5; --seq-550: #1c5cab; --seq-700: #0d366b;
    --good: #0ca30c; --warning: #fab219; --critical: #d03b3b; --good-text: #006300;
    --deemph: #B5B8B3;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      color-scheme: dark;
      --ground: #141715; --surface-1: #1B201D; --panel-2: #232925;
      --text-primary: #E4E8E4; --text-secondary: #9AA49E; --text-muted: #898781;
      --grid: #2C2C2A; --axis: #383835; --border: rgba(255,255,255,0.10);
      --series-1: #3987e5; --series-1-wash: rgba(57,135,229,0.12);
      --seq-100: #104281; --seq-250: #1c5cab; --seq-400: #3987e5; --seq-550: #6da7ec; --seq-700: #b7d3f6;
      --good: #0ca30c; --warning: #fab219; --critical: #d03b3b; --good-text: #0ca30c;
      --deemph: #4A514D;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --ground: #141715; --surface-1: #1B201D; --panel-2: #232925;
    --text-primary: #E4E8E4; --text-secondary: #9AA49E; --text-muted: #898781;
    --grid: #2C2C2A; --axis: #383835; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-1-wash: rgba(57,135,229,0.12);
    --seq-100: #104281; --seq-250: #1c5cab; --seq-400: #3987e5; --seq-550: #6da7ec; --seq-700: #b7d3f6;
    --good: #0ca30c; --warning: #fab219; --critical: #d03b3b; --good-text: #0ca30c;
    --deemph: #4A514D;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--ground); color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif; font-size: 15px; line-height: 1.45; }
  .shell { max-width: 1080px; margin: 0 auto; padding: 0 18px 60px; }
  header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 8px 20px;
    padding: 26px 0 12px; border-bottom: 2px solid var(--text-primary); margin-bottom: 18px; }
  h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.01em; margin: 0; }
  .meta { font-size: 0.78rem; color: var(--text-muted); }
  h2 { font-size: 1rem; font-weight: 700; margin: 26px 0 8px; }
  .sub { font-size: 0.85rem; color: var(--text-secondary); margin: 0 0 10px; }

  /* hero */
  .hero { display: grid; grid-template-columns: minmax(200px, auto) 1fr; gap: 14px 28px; align-items: center;
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 4px; padding: 18px 20px; }
  .hero .fig { font-size: 52px; font-weight: 600; line-height: 1; letter-spacing: -0.02em; }
  .hero .fig small { font-size: 18px; font-weight: 500; color: var(--text-secondary); margin-left: 6px; }
  .hero .lbl { font-size: 0.78rem; color: var(--text-muted); margin-bottom: 4px; }
  .hero p { margin: 0; font-size: 0.92rem; color: var(--text-secondary); }
  .hero p strong { color: var(--text-primary); }
  @media (max-width: 600px) { .hero { grid-template-columns: 1fr; } }

  /* stat tiles */
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin: 14px 0; }
  .tile { background: var(--surface-1); border: 1px solid var(--border); border-radius: 4px; padding: 12px 14px; }
  .tile .lbl { font-size: 0.76rem; color: var(--text-muted); }
  .tile .val { font-size: 1.6rem; font-weight: 600; line-height: 1.15; margin: 2px 0; }
  .tile .val small { font-size: 0.8rem; font-weight: 500; color: var(--text-secondary); margin-left: 4px; }
  .tile .delta { font-size: 0.78rem; color: var(--text-secondary); }
  .tile .delta.up { color: var(--good-text); }
  .status { display: inline-flex; align-items: center; gap: 5px; font-size: 0.74rem; font-weight: 600; }
  .status .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .status.good .dot { background: var(--good); }
  .status.warn .dot { background: var(--warning); }
  .status.crit .dot { background: var(--critical); }

  /* charts */
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
  .chart { background: var(--surface-1); border: 1px solid var(--border); border-radius: 4px; padding: 12px 12px 8px; position: relative; }
  .chart h3 { font-size: 0.82rem; font-weight: 600; margin: 0 0 2px; display: flex; justify-content: space-between; gap: 8px; }
  .chart h3 span { font-weight: 400; color: var(--text-muted); font-size: 0.74rem; }
  .chart svg { width: 100%; height: auto; display: block; overflow: visible; }
  .chart .empty { position: absolute; inset: 40px 12px 30px; display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem; color: var(--text-muted); text-align: center; pointer-events: none; }
  .tip { position: absolute; pointer-events: none; background: var(--surface-1); border: 1px solid var(--border);
    border-radius: 3px; padding: 6px 8px; font-size: 0.76rem; box-shadow: 0 2px 8px rgba(0,0,0,0.12); display: none; z-index: 2; white-space: nowrap; }
  .tip b { font-size: 0.88rem; }
  .tip .k { color: var(--text-secondary); }
  .axis text { fill: var(--text-muted); font-size: 10px; font-variant-numeric: tabular-nums; }
  .grid-line { stroke: var(--grid); stroke-width: 1; }
  .baseline { stroke: var(--axis); stroke-width: 1; }
  .series { fill: none; stroke: var(--series-1); stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
  .area { fill: var(--series-1-wash); }
  .dot { fill: var(--series-1); stroke: var(--surface-1); stroke-width: 2; }
  .target { stroke: var(--text-muted); stroke-width: 1; }
  .target-lbl, .end-lbl { fill: var(--text-secondary); font-size: 10px; }
  .end-lbl { font-weight: 600; fill: var(--text-primary); }
  .crosshair { stroke: var(--axis); stroke-width: 1; display: none; }
  .hit { fill: transparent; }

  /* heat grid */
  table.heat { border-collapse: separate; border-spacing: 2px; font-size: 0.78rem; font-variant-numeric: tabular-nums; }
  table.heat th { font-weight: 500; color: var(--text-muted); text-align: left; padding: 2px 6px 2px 0; font-size: 0.72rem; }
  table.heat td { width: 44px; height: 30px; text-align: center; border-radius: 3px; color: var(--text-primary); cursor: default; }
  table.heat td.l0 { background: var(--panel-2); color: var(--text-muted); }
  table.heat td.l1 { background: var(--seq-100); }
  table.heat td.l2 { background: var(--seq-250); }
  table.heat td.l3 { background: var(--seq-400); color: #fff; }
  table.heat td.l4 { background: var(--seq-550); color: #fff; }
  table.heat td.na { background: transparent; color: var(--text-muted); border: 1px dashed var(--grid); }
  table.heat td:hover { outline: 2px solid var(--text-primary); outline-offset: -2px; }

  /* profile */
  table.prof { width: 100%; border-collapse: collapse; font-size: 0.84rem; font-variant-numeric: tabular-nums; }
  table.prof th { text-align: left; font-size: 0.7rem; color: var(--text-muted); font-weight: 600; padding: 6px 8px 6px 0; border-bottom: 1px solid var(--axis); }
  table.prof td { padding: 7px 8px 7px 0; border-bottom: 1px solid var(--grid); }
  details { margin-top: 8px; }
  summary { font-size: 0.74rem; color: var(--text-muted); cursor: pointer; }
  table.tv { border-collapse: collapse; font-size: 0.76rem; font-variant-numeric: tabular-nums; margin-top: 6px; }
  table.tv th, table.tv td { padding: 3px 10px 3px 0; text-align: left; border-bottom: 1px solid var(--grid); }
  footer { margin-top: 36px; padding-top: 12px; border-top: 2px solid var(--text-primary); font-size: 0.72rem; color: var(--text-muted); line-height: 1.6; }
  a { color: var(--series-1); }
</style>
<div class="shell">
<header>
  <h1>English Season Board</h1>
  <div class="meta" id="meta"></div>
</header>
<div class="hero" id="hero"></div>
<div class="tiles" id="tiles"></div>

<h2>Time trials</h2>
<p class="sub">Each panel is one domain of the diagnostic. The horizontal rule is this season's target (baseline + one noise threshold; floors apply). Movement smaller than the shaded band around the last point is inside noise.</p>
<div class="grid" id="trials"></div>

<h2>Weekly load</h2>
<p class="sub">Adherence, not ability — the first thing to check when a time trial disappoints. Darker = more; the floor per row is in the label. This never feeds the diagnostic.</p>
<div class="chart" id="load"></div>

<h2>Profile — where the season's work goes</h2>
<div class="chart" id="profile"></div>

<footer id="foot"></footer>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  const D = JSON.parse(document.getElementById("data").textContent);
  const $ = (s) => document.querySelector(s);
  const el = (t, a, ...kids) => { const n = document.createElementNS(t.startsWith("svg:") ? "http://www.w3.org/2000/svg" : "http://www.w3.org/1999/xhtml", t.replace("svg:", ""));
    for (const k in a || {}) n.setAttribute(k, a[k]); for (const c of kids) n.append(c); return n; };
  const fmt = (v, unit) => v == null ? "—" : (unit === "families" ? Math.round(v).toLocaleString() : (unit === "MTLD" ? (+v).toFixed(1) : Math.round(v)));
  const S = D.season, trials = D.trials, targets = D.targets;
  const latest = trials[trials.length - 1] || null, prev = trials[trials.length - 2] || null;

  // ---- meta + hero ----
  $("#meta").textContent = "dial " + D.dial + " · generated " + D.generated.slice(0, 10) + " · " + trials.length + " time trial" + (trials.length === 1 ? "" : "s") + " logged";
  const hero = $("#hero");
  if (S.state === "PRE-SEASON") {
    hero.append(el("div", {}, el("div", { class: "lbl" }, "Season"), el("div", { class: "fig" }, "Week 0", el("small", {}, "not started"))),
      el("div", {}, el("p", {}, "The clock starts when row 1 lands in tracking.tsv. ", el("strong", {}, "Run the diagnostic once, rested (~60 min)"), " — targets, the dial, the 12-week calendar and the race date are all computed from that row. Until then this board has nothing to measure.")));
  } else {
    const wk = S.week;
    hero.append(el("div", {}, el("div", { class: "lbl" }, "Season week"), el("div", { class: "fig" }, "Week " + wk, el("small", {}, "of " + D.season_weeks))),
      el("div", {}, el("p", {}, el("strong", {}, S.days_to_trial != null ? (S.days_to_trial >= 0 ? S.days_to_trial + " days to time trial " + (D.trial_weeks.indexOf(S.next_trial_week) + 1) : "time trial week") : "season complete"), " · baseline " + S.baseline + " · race weekend " + S.race + ". Primary target: " + D.primary + " → " + fmt(targets[D.primary], "") + ".")));
  }

  // ---- tiles ----
  const tiles = $("#tiles");
  const thisWeek = D.weekly[D.weekly.length - 1] || null;
  function tile(label, val, unit, sub, cls) {
    const t = el("div", { class: "tile" }, el("div", { class: "lbl" }, label), el("div", { class: "val" }, String(val), el("small", {}, unit || "")));
    if (sub) t.append(el("div", { class: "delta " + (cls || "") }, sub));
    return t;
  }
  const pm = D.metrics.find(m => m.key === D.primary);
  if (latest) {
    const v = latest[D.primary], t = targets[D.primary], d = prev ? v - prev[D.primary] : null;
    tiles.append(tile("Primary target · " + pm.label, fmt(v, pm.unit), pm.unit, "target " + fmt(t, pm.unit) + (d != null ? " · " + (d >= 0 ? "+" : "") + fmt(d, pm.unit) + " vs last trial" : " · baseline"), d != null && d >= D.noise[D.primary] ? "up" : ""));
  } else {
    tiles.append(tile("Primary target · " + pm.label, "—", pm.unit, "set at baseline"));
  }
  const fl = D.load_floor;
  const lv = (k) => thisWeek && thisWeek[k] !== "" && thisWeek[k] != null ? +thisWeek[k] : null;
  const st = (k) => { const v = lv(k); if (v == null) return ["warn", "unreported"]; return v >= fl[k] ? ["good", "floor met"] : ["crit", "below floor " + fl[k]]; };
  for (const [k, label] of [["conversations", "Conversations this week"], ["srs_days", "SRS review days"], ["recordings", "Recorded speaking"]]) {
    const [cls, txt] = st(k);
    const t = tile(label, lv(k) == null ? "—" : lv(k), "/ " + fl[k], null);
    t.append(el("div", { class: "status " + cls }, el("span", { class: "dot" }), txt));
    tiles.append(t);
  }
  if (D.anki) {
    const c = D.anki.counts || {};
    tiles.append(tile("Deck", (c.total || 0), "cards", (c.new || 0) + " new · " + (c.young || 0) + " young · " + (c.mature || 0) + " mature · stats " + (D.anki.exported || "").slice(0, 10)));
  }

  // ---- time trial small multiples ----
  const tip = el("div", { class: "tip" }); document.body.append(tip);
  function showTip(x, y, rows) { tip.replaceChildren(); rows.forEach(r => { const d = el("div"); const b = el("b"); b.textContent = r[0]; const k = el("span", { class: "k" }); k.textContent = " " + r[1]; d.append(b, k); tip.append(d); });
    tip.style.display = "block"; const w = tip.offsetWidth, h = tip.offsetHeight; tip.style.left = Math.min(x + 12, window.innerWidth - w - 8) + "px"; tip.style.top = (y - h - 12) + "px"; }
  const hideTip = () => tip.style.display = "none";

  const grid = $("#trials");
  for (const m of D.metrics) {
    const card = el("div", { class: "chart" });
    const tgt = targets[m.key];
    card.append(el("h3", {}, m.label, el("span", {}, tgt != null ? "target " + fmt(tgt, m.unit) + " " + m.unit : "target set at baseline")));
    const pts = trials.map((r, i) => ({ i, date: r.date, v: r[m.key] })).filter(p => p.v != null);
    const W = 300, H = 150, L = 34, R = 40, T = 10, B = 24;
    const svg = el("svg:svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": m.label + " over time trials" });
    const vals = pts.map(p => p.v).concat(tgt != null ? [tgt] : []);
    const nz = D.noise[m.key] || 0;
    let lo = vals.length ? Math.min(...vals) : 0, hi = vals.length ? Math.max(...vals) : 1;
    if (!vals.length) { lo = 0; hi = 1; }
    const pad = Math.max((hi - lo) * 0.25, nz || (hi - lo) * 0.25 || 1);
    lo = Math.max(0, lo - pad); hi = hi + pad;
    const xs = (i) => L + (D.trial_weeks.length ? (i / Math.max(1, D.trial_weeks.length)) * (W - L - R) : 0);
    const ys = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    // gridlines
    for (let g = 0; g <= 3 && vals.length; g++) { const v = lo + (hi - lo) * g / 3; svg.append(el("svg:line", { x1: L, x2: W - R, y1: ys(v), y2: ys(v), class: "grid-line" }));
      const t = el("svg:text", { x: L - 4, y: ys(v) + 3, "text-anchor": "end", class: "axis" }); t.textContent = fmt(v, m.unit); const gA = el("svg:g", { class: "axis" }, t); svg.append(gA); }
    // x labels: baseline, TT1, TT2, TT3
    ["base", ...D.trial_weeks.map(w => "w" + w)].forEach((lab, i) => { const t = el("svg:text", { x: xs(i), y: H - 6, "text-anchor": "middle" }); t.textContent = lab; svg.append(el("svg:g", { class: "axis" }, t)); });
    if (tgt != null) { svg.append(el("svg:line", { x1: L, x2: W - R, y1: ys(tgt), y2: ys(tgt), class: "target" }));
      const t = el("svg:text", { x: W - R + 4, y: ys(tgt) + 3, class: "target-lbl" }); t.textContent = "target"; svg.append(t); }
    if (pts.length) {
      const last = pts[pts.length - 1];
      if (nz) svg.append(el("svg:rect", { x: L, width: W - L - R, y: ys(last.v + nz), height: Math.max(0, ys(last.v - nz) - ys(last.v + nz)), class: "area" }));
      const d = pts.map((p, k) => (k ? "L" : "M") + xs(p.i) + " " + ys(p.v)).join(" ");
      if (pts.length > 1) svg.append(el("svg:path", { d, class: "series" }));
      pts.forEach(p => svg.append(el("svg:circle", { cx: xs(p.i), cy: ys(p.v), r: 4, class: "dot" })));
      const t = el("svg:text", { x: xs(last.i) + 8, y: ys(last.v) - 8, class: "end-lbl" }); t.textContent = fmt(last.v, m.unit); svg.append(t);
      // crosshair + hit layer
      const ch = el("svg:line", { y1: T, y2: H - B, class: "crosshair" }); svg.append(ch);
      const hit = el("svg:rect", { x: L, y: 0, width: W - L - R, height: H, class: "hit" }); svg.append(hit);
      const near = (ev) => { const r = svg.getBoundingClientRect(); const px = (ev.clientX - r.left) / r.width * W; let best = pts[0]; for (const p of pts) if (Math.abs(xs(p.i) - px) < Math.abs(xs(best.i) - px)) best = p; return best; };
      hit.addEventListener("pointermove", ev => { const p = near(ev); ch.setAttribute("x1", xs(p.i)); ch.setAttribute("x2", xs(p.i)); ch.style.display = "block";
        showTip(ev.clientX, ev.clientY, [[fmt(p.v, m.unit) + " " + m.unit, p.date], ...(tgt != null ? [[fmt(tgt, m.unit), "target"]] : [])]); });
      hit.addEventListener("pointerleave", () => { ch.style.display = "none"; hideTip(); });
    }
    card.append(svg);
    if (!pts.length) card.append(el("div", { class: "empty" }, "no time trials yet — target and trajectory appear after the baseline"));
    // table view
    const det = el("details", {}, el("summary", {}, "table view"));
    const tv = el("table", { class: "tv" }, el("tr", {}, el("th", {}, "date"), el("th", {}, m.label), el("th", {}, "Δ vs previous"), el("th", {}, "target")));
    pts.forEach((p, k) => { const dv = k ? p.v - pts[k - 1].v : null; tv.append(el("tr", {}, el("td", {}, p.date), el("td", {}, fmt(p.v, m.unit)), el("td", {}, dv == null ? "—" : (dv >= 0 ? "+" : "") + fmt(dv, m.unit) + (nz && Math.abs(dv) >= nz ? " ✓ signal" : (dv == null ? "" : " (noise)"))), el("td", {}, fmt(tgt, m.unit)))); });
    det.append(tv); card.append(det); grid.append(card);
  }

  // ---- weekly load heat grid ----
  const load = $("#load");
  const rows = [["conversations", "Conversations ≥2"], ["srs_days", "SRS days ≥5"], ["recordings", "Recordings ≥1"], ["listening_days", "Listening days ≥5"]];
  if (!D.weekly.length) {
    load.append(el("p", { class: "sub", style: "margin:6px 0" }, "No weekly rows yet. The Friday review writes one row per week from Anki stats, practice recordings and your close-of-week report."));
  } else {
    const tbl = el("table", { class: "heat" });
    const head = el("tr", {}, el("th", {}, "")); D.weekly.forEach(w => head.append(el("th", {}, w.week_start.slice(5)))); tbl.append(head);
    for (const [k, label] of rows) {
      const tr = el("tr", {}, el("th", {}, label));
      D.weekly.forEach(w => {
        const raw = w[k]; const v = raw === "" || raw == null ? null : +raw; const f = D.load_floor[k];
        let cls = "na"; if (v != null) { const r = v / f; cls = v === 0 ? "l0" : r < 0.5 ? "l1" : r < 1 ? "l2" : r < 1.5 ? "l3" : "l4"; }
        const td = el("td", { class: cls, tabindex: "0" }); td.textContent = v == null ? "?" : v;
        const show = (ev) => showTip(ev.clientX || 0, ev.clientY || 0, [[v == null ? "unreported" : v + " / floor " + f, label], ["week of " + w.week_start, w.dial ? "dial " + w.dial : ""]]);
        td.addEventListener("pointermove", show); td.addEventListener("focus", show); td.addEventListener("pointerleave", hideTip); td.addEventListener("blur", hideTip);
        tr.append(td);
      });
      tbl.append(tr);
    }
    const fr = el("tr", {}, el("th", {}, "Floor"));
    D.weekly.forEach(w => { const ok = w.floor_ok; const cls = ok === "yes" ? "good" : ok === "no" ? "crit" : "warn"; fr.append(el("td", { class: "na", style: "border:none" }, el("span", { class: "status " + cls }, el("span", { class: "dot" }), ok === "yes" ? "met" : ok === "no" ? "missed" : "partial"))); });
    tbl.append(fr);
    load.append(el("div", { style: "overflow-x:auto" }, tbl));
    if (D.practice.length) load.append(el("p", { class: "sub", style: "margin:8px 0 0" }, D.practice.length + " practice recordings on file; latest " + D.practice[D.practice.length - 1].date + " at " + (D.practice[D.practice.length - 1].wpm || "—") + " wpm."));
  }

  // ---- profile ----
  const prof = $("#profile");
  const tbl = el("table", { class: "prof" }, el("tr", {}, el("th", {}, "Domain"), el("th", {}, "Latest"), el("th", {}, "vs previous"), el("th", {}, "Target"), el("th", {}, "Read")));
  for (const m of D.metrics) {
    const v = latest ? latest[m.key] : null, p = prev ? prev[m.key] : null, t = targets[m.key];
    const dv = v != null && p != null ? v - p : null; const nz = D.noise[m.key] || 0;
    let read = "—";
    if (v != null) { read = t != null && v >= t ? "target met" : (m.key === D.primary ? "primary target — the dial is pointed here" : (dv == null ? "baseline" : (Math.abs(dv) >= nz ? (dv > 0 ? "real gain" : "real drop") : "flat (inside noise)"))); }
    const dcell = el("td", {}); dcell.textContent = dv == null ? "—" : (dv >= 0 ? "+" : "") + fmt(dv, m.unit) + (nz && dv != null ? (Math.abs(dv) >= nz ? " ✓" : " ~") : "");
    tbl.append(el("tr", {}, el("td", {}, m.label + (m.key === D.primary ? " ★" : "")), el("td", {}, fmt(v, m.unit) + (v != null ? " " + m.unit : "")), dcell, el("td", {}, fmt(t, m.unit)), el("td", {}, read)));
  }
  prof.append(tbl);
  const o = D.observations;
  prof.append(el("p", { class: "sub", style: "margin:10px 0 0" }, "Observation log: " + (o.PROMOTED + o.PATTERN) + " active patterns · " + o.WATCHING + " watching · " + o.STRENGTH + " strengths · " + o.RETIRED + " retired. Dial " + D.dial + " → accountable metric " + D.primary + ". " + (latest ? "" : "Profile fills in at baseline.")));

  $("#foot").append(el("div", {}, "Data: tracking.tsv (time trials) · logs/weekly.tsv (load) · logs/dial-log.tsv · logs/anki-stats.json · logs/practice/ · observations.md. Rebuilt by scripts/build-progress.py at every Friday review and after every diagnostic."),
    el("div", {}, "Targets = baseline + one noise threshold (docs/TARGET.md). Load never feeds the diagnostic. Repeat scores are floors — upward moves are trusted, flat ones ambiguous."));
})();
</script>
</html>
"""

def build(repo=REPO, out=OUT, today=None):
    data = load_data(repo, today)
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    out.write_text(html, encoding="utf-8")
    return data

def selftest():
    import tempfile, shutil
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td); (td / "logs").mkdir()
        # pre-season
        (td / "tracking.tsv").write_text("date\tctest_pct\tvocab_size\tdict_pct\tei_pct\twpm\tmtld\tbeyond_core_pct\tevidence_n\n")
        d = build(td, td / "p.html", today=dt.date(2026, 9, 9))
        assert d["season"]["state"] == "PRE-SEASON" and d["targets"] == {}
        # in-season with two trials
        (td / "tracking.tsv").write_text("date\tctest_pct\tvocab_size\tdict_pct\tei_pct\twpm\tmtld\tbeyond_core_pct\tevidence_n\n"
                                          "2026-09-13\t70\t5200\t82\t60\t104\t52.0\t18\t6\n2026-10-17\t74\t5400\t88\t65\t117\t55.0\t19\t8\n")
        d = build(td, td / "p.html", today=dt.date(2026, 10, 20))
        s = d["season"]
        assert s["start"] == "2026-09-14" and s["week"] == 6, s
        assert d["targets"]["wpm"] == 120 and d["targets"]["dict_pct"] == 92 and d["targets"]["ctest_pct"] == 78 and d["targets"]["evidence_n"] == 10, d["targets"]
        assert s["next_trial_week"] == 10 and s["race"] == "2026-12-05", s
        html = (td / "p.html").read_text()
        assert "__DATA__" not in html and '"wpm": 117.0' in html
    print("build-progress.py selftest: OK")

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        d = build()
        print(f"progress.html written — season {d['season']['state']}, {len(d['trials'])} trials, {len(d['weekly'])} weekly rows")
