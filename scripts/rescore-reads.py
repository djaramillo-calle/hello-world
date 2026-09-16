#!/usr/bin/env python3
"""Re-score existing read-alouds against the SPAN he actually read.

    .venv-practice/bin/python scripts/rescore-reads.py [--dry] [--only 2026-09-15] [--limit N]

Why this exists (2026-09-16). `detect_passage` returned ONE book chunk, and he reads a run of them
in a sitting. So Azure scored the whole recording against ~160 words of reference: 9:1 on the
twelve-minute read, 57:1 on the eighty-four-minute one, and on 2026-09-15 the chunk it picked was
not even where he started. Every row in the anchor series was measured that way.

`detect_span` finds the run (bigram coverage; see practice-ingest). This re-runs the Azure
assessment for each stored read with the right reference and rewrites the record, REUSING the
stored Whisper transcript — the transcription does not change, only what it is scored against.

It needs the audio, which lives on Drive, and it spends the recording's duration again against the
Azure free tier. `--dry` reports what it would do and calls nothing.
"""
import argparse, importlib.util, json, pathlib, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
PRACTICE = REPO / "logs" / "practice"
sys.path.insert(0, str(REPO / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def reads(only=None):
    """Every stored read-aloud that has a transcript beside it, oldest first."""
    out = []
    for f in sorted(PRACTICE.glob("*.json")):
        if f.name.endswith(".review.json") or f.name.startswith("."):
            continue
        if only and only not in f.name:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        txt = f.with_suffix(".txt")
        if d.get("kind") == "read" and txt.exists():
            out.append((f, d, txt.read_text(encoding="utf-8")))
    return out


def plan(only=None, pi=None):
    """What each read WOULD be scored against now, without touching Azure or Drive."""
    pi = pi or _load("practice-ingest")
    rows = []
    for f, d, tr in reads(only):
        first, last, text, cover = pi.detect_span(tr)
        rows.append({
            "file": f, "record": d, "source": d.get("source"),
            "was": d.get("passage"), "was_ref": len((pi.passage_text(d.get("passage")) or "").split()),
            "first": first, "last": last, "reference": text, "cover": cover,
            "spoken": len(tr.split()), "ref": len((text or "").split()),
            "locale": (d.get("azure") or {}).get("locale"),
        })
    return rows


def stamp(name):
    """The recorder's timestamp inside a file name — the only part that is stable.

    The stored `source` is not always the name on Drive: practice-ingest normalises it, so
    "eng read B006 - 2026_09_10_21_35_11.mp3" is recorded as "eng read - 2026_09_10_21_35_11.mp3"
    and an exact-name lookup finds nothing."""
    import re
    m = re.search(r"\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}", name or "")
    return m.group(0) if m else None


def fetch(source, dest, drv=None):
    """The original audio from the recording roots on Drive, matched by name or by timestamp."""
    cs = _load("cloud-sync")
    if drv is None:
        import drive
        drv = cs.Drive(drive.load_key())
    want = stamp(source)
    for root in cs.RECORDING_ROOTS:
        folders = drv.resolve_all(root) if hasattr(drv, "resolve_all") else [drv.resolve(root)]
        for folder in [x for x in folders if x]:
            for rel, f in drv.walk(folder["id"]):
                if f["name"] == source or (want and stamp(f["name"]) == want and "duplicate" not in f["name"]):
                    drv.download(f["id"], dest)
                    return dest
    return None


def rescore(row, pi, azure_pa, work):
    """One read: re-run the assessment against the span and rewrite the record in place.

    The same word-count guard the ingest uses: a reference that is not roughly what he said must
    never be scored scripted, or this tool would spend Azure minutes re-creating the very fault it
    exists to repair."""
    ok, ratio = pi.ref_ratio_ok(row["spoken"], row["reference"])
    if not ok:
        return None, (f"{row['file'].name[:10]} {row['first']}–{row['last']}: {row['spoken']} words said "
                      f"against {row['ref']} of reference (ratio {ratio}) — refused, not rescored")
    audio = fetch(row["source"], work / ("audio" + pathlib.Path(row["source"]).suffix))
    if not audio:
        return None, f"{row['source']}: not on Drive any more — skipped"
    wav = work / "rec.wav"
    pi.to_wav(audio, wav)
    r = azure_pa.dual_locale_assessment(str(wav), reference_text=row["reference"])
    d = row["record"]
    d["azure"] = r
    d["passage"] = row["first"]
    d["scripted"] = True
    d["passage_overlap"] = row["cover"]
    d["span"] = {"first": row["first"], "last": row["last"], "cover": row["cover"],
                 "ref_words": row["ref"], "ratio": ratio}
    d["kind_note"] = (f"rescored {row['first']}–{row['last']} ({row['cover']:.0%} bigram cover, "
                      f"{row['ref']} reference words); was {row['was']} alone ({row['was_ref']} words)")
    d["rescored"] = True
    row["file"].write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    gb = (r.get("en_gb") or {}).get("overall") or {}
    return True, (f"{row['file'].name[:10]} {row['first']}–{row['last']}: accuracy {gb.get('accuracy')} "
                  f"fluency {gb.get('fluency')} completeness {gb.get('completeness')} prosody {gb.get('prosody')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry", action="store_true", help="report the spans and call nothing")
    ap.add_argument("--only", help="substring of the log file name")
    ap.add_argument("--limit", type=int, help="stop after this many")
    ap.add_argument("--force", action="store_true",
                    help="re-assess even a record already scored in the target locale")
    a = ap.parse_args()
    pi = _load("practice-ingest")
    azure_pa = _load("azure_pa")
    rows = [r for r in plan(a.only, pi) if r["first"]]
    # A record already carrying the locale we would score it in has nothing to gain and costs its
    # own duration against the quota. Skip it unless asked. (The 09-10 read was rescored on its
    # own on 2026-09-16 to measure the en-GB -> en-US difference; the rest followed after.)
    if not a.force:
        skip = [r for r in rows if r["locale"] == azure_pa.LOCALE]
        rows = [r for r in rows if r["locale"] != azure_pa.LOCALE]
        for r in skip:
            print(f"  {r['file'].name[:10]}: already {azure_pa.LOCALE} — skipped (--force to redo)")
    if not rows:
        print("rescore-reads: nothing with a detectable span (is library/ present?)")
        return 3
    total = sum(r["record"].get("duration_s") or 0 for r in rows) / 60
    print(f"rescore-reads: {len(rows)} read(s), {total:.0f} minutes of audio to re-assess")
    for r in rows:
        print(f"  {r['file'].name[:10]}  {r['was']} ({r['was_ref']}w) → {r['first']}–{r['last']} "
              f"({r['ref']}w, {r['cover']:.0%} cover), spoken {r['spoken']}w, "
              f"ratio {r['spoken'] / max(1, r['ref']):.2f}"
              f"{'' if pi.ref_ratio_ok(r['spoken'], r['reference'])[0] else '  ← OUT OF BAND, will be refused'}")
    if a.dry:
        return 0
    # to_wav shells out to ffmpeg, which lives in the practice venv — cloud-sync puts it on PATH
    # and a direct run must do the same.
    venv_bin = REPO / ".venv-practice" / "bin"
    if venv_bin.is_dir():
        import os
        os.environ["PATH"] = f"{venv_bin}:{os.environ.get('PATH', '')}"
    done = 0
    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td)
        for r in rows:
            if a.limit and done >= a.limit:
                break
            try:
                ok, msg = rescore(r, pi, azure_pa, work)
                print("  " + msg)
                done += 1 if ok else 0      # a missing recording is skipped, not rescored
            except Exception as e:
                print(f"  {r['file'].name[:10]}: FAILED — {type(e).__name__}: {str(e)[:160]}")
                break          # a quota or credential failure will hit every one; stop, do not burn them
    print(f"rescore-reads: {done} rescored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
