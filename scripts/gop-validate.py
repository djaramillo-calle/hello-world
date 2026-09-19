#!/usr/bin/env python3
"""Measure the local GOP scorer against HUMAN pronunciation scores (speechocean762).

    .venv-gop/bin/python scripts/gop-validate.py --n 300 [--out logs/gop/validate.json]

The primary criterion in docs/GOP.md. speechocean762 carries human accuracy/fluency/prosody/
total per utterance and a 0-2 accuracy per phone, so this measures the scorer against PEOPLE.
Azure gets measured on the SAME utterances when its quota is back, and the two are compared
through the humans — never against each other. "GOP agrees with Azure" is a statement about
agreement, not correctness, and Azure has already been wrong here once.

KNOWN LIMIT, and it must travel with the number: speechocean762 is L1-Mandarin speakers, many
of them children. It validates the METHOD, not the fit to one adult L1-Spanish speaker. His own
six reads are the secondary set for that, and they are six.
"""
import argparse, io, json, pathlib, sys, time

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO / "logs" / "gop" / "validate.json"


def load(n, split="test", seed=0):
    import datasets
    ds = datasets.load_dataset("mispeech/speechocean762", split=split)
    ds = ds.cast_column("audio", datasets.Audio(decode=False))
    if n and n < len(ds):
        ds = ds.shuffle(seed=seed).select(range(n))   # seeded: the sample is reproducible
    return ds


def run(n=300, out=DEFAULT_OUT, split="test", seed=0, log=print):
    import soundfile as sf, numpy as np, importlib.util
    spec = importlib.util.spec_from_file_location("gop", REPO / "scripts" / "gop.py")
    gop = importlib.util.module_from_spec(spec); spec.loader.exec_module(gop)
    ds = load(n, split, seed)
    sc = gop.Scorer()
    rows, secs, t0 = [], 0.0, time.time()
    for i, r in enumerate(ds):
        a, sr = sf.read(io.BytesIO(r["audio"]["bytes"]), dtype="float32")
        secs += len(a) / sr
        try:
            g = sc.score(a, r["text"])
        except Exception as e:
            log(f"  [{i}] failed: {type(e).__name__}: {str(e)[:90]}"); continue
        rows.append({"i": i, "speaker": r["speaker"], "age": r["age"], "text": r["text"],
                     "gop_accuracy": g["accuracy"], "gop_completeness": g["completeness"],
                     "n_phones": g["n_phones"], "aligned": g["aligned"],
                     "human_accuracy": r["accuracy"], "human_total": r["total"],
                     "human_fluency": r["fluency"], "human_prosodic": r["prosodic"],
                     "human_completeness": r["completeness"]})
        if (i + 1) % 50 == 0:
            log(f"  {i + 1}/{len(ds)} ...")
    el = time.time() - t0
    ok = [r for r in rows if r["gop_accuracy"] is not None]
    from scipy.stats import pearsonr, spearmanr
    g = np.array([r["gop_accuracy"] for r in ok], float)
    stats = {"n": len(ok), "audio_s": round(secs, 1), "wall_s": round(el, 1),
             "realtime_x": round(secs / max(el, 1e-9), 1),
             "gop_accuracy": {"min": float(g.min()), "max": float(g.max()),
                              "mean": round(float(g.mean()), 2), "sd": round(float(g.std()), 2)}}
    for key in ("human_accuracy", "human_total", "human_fluency", "human_prosodic"):
        h = np.array([r[key] for r in ok], float)
        stats[key] = {"pearson": round(float(pearsonr(g, h)[0]), 3),
                      "spearman": round(float(spearmanr(g, h)[0]), 3),
                      "range": [float(h.min()), float(h.max())]}
    payload = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "dataset": "mispeech/speechocean762", "split": split, "seed": seed,
               "model": gop.MODEL, "stats": stats, "rows": ok,
               "note": ("Human scores are 0-10 (phones 0-2). L1-Mandarin speakers, many children "
                        "- this validates the METHOD, not the fit to one adult L1-Spanish reader. "
                        "Azure's numbers on this same sample go in alongside when its quota is back; "
                        "both are compared to the humans, never to each other.")}
    out = pathlib.Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"gop-validate: {len(ok)} utterances, {secs:.0f}s audio in {el:.0f}s ({stats['realtime_x']}x realtime)")
    for key in ("human_accuracy", "human_total", "human_fluency", "human_prosodic"):
        s = stats[key]
        log(f"  vs {key:18s} pearson {s['pearson']:+.3f}  spearman {s['spearman']:+.3f}  (human range {s['range'][0]:.0f}-{s['range'][1]:.0f})")
    log(f"  -> {out}")
    return payload


def selftest():
    assert DEFAULT_OUT.name.endswith(".json")
    import inspect
    assert "shuffle(seed=seed)" in inspect.getsource(load), "the sample must be reproducible"
    assert "seed" in inspect.signature(load).parameters
    src = inspect.getsource(run)
    for key in ("human_accuracy", "human_total", "human_fluency", "human_prosodic"):
        assert key in src, f"{key} is part of the pre-registered comparison"
    assert "note" in src, "the L1-Mandarin/children caveat must ship inside the payload"
    print("gop-validate.py selftest: OK"); return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--split", default="test")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    run(a.n, a.out, a.split, a.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
