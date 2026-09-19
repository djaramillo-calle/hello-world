#!/usr/bin/env python3
"""Goodness of Pronunciation — local, per-phoneme pronunciation scoring.

    .venv-gop/bin/python scripts/gop.py --wav a.wav --text "what he should have said"
    .venv-gop/bin/python scripts/gop.py --selftest

Why this exists (2026-09-19): Azure's F0 tier ran out after eight days and S0 bills
~$1.30 an audio hour with no free allowance. This costs nothing per run and cannot run out.
`docs/GOP.md` holds the pre-registered protocol — READ IT before drawing any conclusion from
these numbers; they are in validation, not in service.

The method (Witt & Young's GOP, computed on a CTC phoneme recogniser):

  1. espeak-ng turns the reference text into the canonical IPA phones the speaker SHOULD say.
     en-us, matching how facebook/wav2vec2-lv-60-espeak-cv-ft was phonemised in training — a
     different G2P would put symbols in the sequence the model never learned to emit.
  2. The model gives a log-posterior over 392 IPA symbols for every 20ms frame.
  3. CTC forced alignment pins each canonical phone to its frames.
  4. GOP(p) = mean over those frames of  log P(p | frame) - max_q log P(q | frame).
     Zero means the model's best guess WAS the expected phone; more negative means the audio
     supported something else more. It is a log ratio, so it has no natural scale — `score`
     is a convenience mapping for reading, never the thing to correlate on.

SCOPE, and it matters: this produces accuracy and the per-phoneme scores. It does NOT produce
fluency, prosody, or completeness, and must never be presented as if it did — that is exactly
the mistake en-GB's unsupported prosody number caused on 09-14.
"""
import argparse, json, math, sys

MODEL = "facebook/wav2vec2-lv-60-espeak-cv-ft"
SR = 16000
# espeak marks stress and length; the model's vocabulary does not carry stress marks, so they
# are stripped before lookup. ᵻ is espeak's reduced vowel, which the model spells ɨ.
STRIP = "ˈˌ"


def _drop(ch):
    """Stress marks and combining diacritics: espeak writes them, the model has no unit for them."""
    import unicodedata
    return ch in STRIP or unicodedata.combining(ch) != 0
FOLD = {"ᵻ": "ɨ", "ɚ": "ɹ", "ɐ": "ʌ"}


def phonemize(text, lang="en-us", multi=None):
    """Reference text -> list of canonical IPA phones, words kept separate.

    `multi` is the set of two-character symbols to keep whole. Scorer passes the MODEL's own
    two-character vocabulary, so the splitter can never emit a symbol the model has no output
    unit for. Checked on 1,094 words of the book: 5 stray symbols in 5,006, all from combining
    marks and from ɪə, which espeak writes and this model does not have.
    """
    from phonemizer.backend import EspeakBackend
    be = EspeakBackend(lang, with_stress=False)
    out = []
    for word in be.phonemize([text], strip=True)[0].split():
        phones = [FOLD.get(c, c) for c in _split_ipa(word, multi or MULTI)]
        if phones:
            out.append(phones)
    return out


# Two-character phones espeak emits for en-us. Longest-match matters: a naive "join this char
# with the next if the next is a length mark or a glide" turned "ðə" into one symbol the model
# has never emitted, and every word starting with a consonant + schwa scored as a hole.
MULTI = ("iː", "uː", "ɑː", "ɔː", "ɜː", "ɛː", "oː", "aɪ", "eɪ", "ɔɪ", "aʊ", "oʊ", "əʊ",
         "ɪə", "ɛə", "ʊə", "dʒ", "tʃ", "aɪ", "ɔː")


def _split_ipa(s, multi=MULTI):
    """Split an espeak word into the symbols the model's vocabulary actually uses."""
    out, i = [], 0
    while i < len(s):
        if _drop(s[i]):
            i += 1; continue
        if i + 1 < len(s) and s[i:i + 2] in multi:
            out.append(s[i:i + 2]); i += 2
            continue
        if s[i] == "\u02d0" and out:
            # a length mark whose vowel was not a two-character unit. Lengthen the vowel if the
            # model has that unit, otherwise drop the mark — a bare ː is not a phone and asking
            # the model for one scores a hole the speaker never made.
            out[-1] = out[-1] + "\u02d0" if out[-1] + "\u02d0" in multi else out[-1]
            i += 1; continue
        if s[i] == "\u02d0":
            i += 1; continue
        out.append(s[i]); i += 1
    return out


def ctc_align(logp, ids, blank=0):
    """Viterbi over the CTC-extended label sequence. Returns a frame->label-index list.

    Standard CTC alignment: the extended sequence interleaves blanks (b l1 b l2 ... b), a frame
    may stay put, step one, or skip a blank between two DIFFERENT labels. Frames landing on a
    blank belong to no phone and are dropped from the score.
    """
    import numpy as np
    T = logp.shape[0]
    ext = [blank]
    for i in ids:
        ext += [i, blank]
    S = len(ext)
    NEG = -1e30
    dp = np.full((T, S), NEG, dtype=np.float64)
    bp = np.zeros((T, S), dtype=np.int32)
    dp[0, 0] = logp[0, ext[0]]
    if S > 1:
        dp[0, 1] = logp[0, ext[1]]
    for t in range(1, T):
        prev = dp[t - 1]
        stay = prev
        step = np.concatenate(([NEG], prev[:-1]))
        skip = np.full(S, NEG)
        if S > 2:
            allowed = np.array([s >= 2 and ext[s] != blank and ext[s] != ext[s - 2] for s in range(S)])
            cand = np.concatenate(([NEG, NEG], prev[:-2]))
            skip = np.where(allowed, cand, NEG)
        best = np.vstack([stay, step, skip])
        bp[t] = best.argmax(axis=0)
        dp[t] = best.max(axis=0) + logp[t, ext]
    s = S - 1 if S == 1 or dp[T - 1, S - 1] >= dp[T - 1, S - 2] else S - 2
    path = [0] * T
    for t in range(T - 1, -1, -1):
        path[t] = s
        s -= int(bp[t][s])
    return path, ext


def gop_from_logp(logp, words, vocab, blank=0):
    """Per-phone GOP for a phonemised reference against one utterance's frame log-posteriors."""
    import numpy as np
    flat = [(w, p) for w, ps in enumerate(words) for p in ps]
    ids = [vocab.get(p, vocab.get("<unk>", blank)) for _, p in flat]
    path, ext = ctc_align(logp, ids, blank)
    frames = {}
    for t, s in enumerate(path):
        if ext[s] == blank:
            continue
        frames.setdefault((s - 1) // 2, []).append(t)
    best = logp.max(axis=1)
    out = []
    for k, (w, p) in enumerate(flat):
        ts = frames.get(k, [])
        if not ts:
            out.append({"phone": p, "word": w, "gop": None, "score": None, "frames": 0})
            continue
        g = float(np.mean([logp[t, ids[k]] - best[t] for t in ts]))
        out.append({"phone": p, "word": w, "gop": round(g, 4),
                    "score": round(100.0 * math.exp(g), 1), "frames": len(ts)})
    return out


class Scorer:
    """Holds the model so a batch of utterances loads it once."""

    def __init__(self, model=MODEL):
        from transformers import AutoProcessor, AutoModelForCTC
        self.proc = AutoProcessor.from_pretrained(model)
        self.model = AutoModelForCTC.from_pretrained(model)
        self.model.eval()
        self.vocab = self.proc.tokenizer.get_vocab()
        self.blank = self.model.config.pad_token_id or 0
        # the splitter's alphabet IS the model's, so a reference can never ask for a unit the
        # model cannot emit (which would read as a mispronunciation the speaker never made)
        self.multi = tuple(k for k in self.vocab if len(k) == 2)

    def logp(self, audio):
        import torch
        with torch.no_grad():
            x = self.proc(audio, sampling_rate=SR, return_tensors="pt").input_values
            return torch.log_softmax(self.model(x).logits[0], dim=-1).numpy().astype("float64")

    def score(self, audio, text):
        words = phonemize(text, multi=self.multi)
        lp = self.logp(audio)
        phones = gop_from_logp(lp, words, self.vocab, self.blank)
        scored = [p for p in phones if p["gop"] is not None]
        return {
            "phones": phones,
            "n_phones": len(phones),
            "aligned": len(scored),
            # NO completeness. It was here, defined as aligned/total, and measurement on 300
            # utterances returned exactly 100.0 every single time — of course it did: CTC forced
            # alignment must traverse every state, so every phone gets frames whatever the audio
            # says. A number that cannot vary is not a measurement. Real completeness needs a FREE
            # decode compared against the reference to catch skipped words; that is unbuilt.
            "accuracy": round(sum(p["score"] for p in scored) / len(scored), 1) if scored else None,
        }


def load_wav(path):
    import soundfile as sf, librosa
    a, sr = sf.read(str(path), dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    return librosa.resample(a, orig_sr=sr, target_sr=SR) if sr != SR else a


def selftest():
    """No model, no audio, no network: the alignment and the phonemiser are the fragile parts."""
    import numpy as np
    vocab = {"<pad>": 0, "a": 1, "b": 2}
    # three frames of 'a' then three of 'b', spoken exactly as written
    T, V = 6, 3
    lp = np.full((T, V), -10.0)
    for t in range(3): lp[t, 1] = -0.01
    for t in range(3, 6): lp[t, 2] = -0.01
    r = gop_from_logp(lp, [["a"], ["b"]], vocab, blank=0)
    assert len(r) == 2 and all(x["gop"] is not None for x in r), r
    assert all(x["gop"] > -0.1 for x in r), r        # said what was expected -> GOP near 0
    # now the second phone is not there: the audio says 'a' throughout
    lp2 = np.full((T, V), -10.0)
    for t in range(T): lp2[t, 1] = -0.01
    r2 = gop_from_logp(lp2, [["a"], ["b"]], vocab, blank=0)
    assert r2[1]["gop"] < r[1]["gop"], (r2, r)        # and it must score WORSE than when present
    assert _split_ipa("dʒʌdʒ") == ["dʒ", "ʌ", "dʒ"], _split_ipa("dʒʌdʒ")
    assert _split_ipa("biː") == ["b", "iː"], _split_ipa("biː")
    assert _split_ipa("ðə") == ["ð", "ə"], _split_ipa("ðə")      # the bug that made every
    assert _split_ipa("θɪn") == ["θ", "ɪ", "n"], _split_ipa("θɪn")  # consonant+schwa a hole
    assert _split_ipa("n\u0329") == ["n"], _split_ipa("n\u0329")      # combining marks dropped
    assert _split_ipa("\u0254\u02d0", ("i\u02d0",)) == ["\u0254"], _split_ipa("\u0254\u02d0", ("i\u02d0",))
    assert _split_ipa("i\u02d0", ("i\u02d0",)) == ["i\u02d0"]        # ...but kept when it is one
    try:
        w = phonemize("the thin judge")
        assert w and all(isinstance(x, list) and x for x in w), w
        assert "ð" in w[0], w
    except RuntimeError as e:
        print(f"gop.py selftest: espeak-ng missing ({e}); alignment checks passed")
        return 0
    print("gop.py selftest: OK")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--wav"); ap.add_argument("--text")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not (a.wav and a.text):
        print("gop.py: need --wav and --text (or --selftest)"); return 2
    r = Scorer().score(load_wav(a.wav), a.text)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
