"""Azure Pronunciation Assessment for the practice loop — dual-locale design.

Locale facts (verified against Azure docs, 2026-08):
- en-GB: word-level accuracy + Mispronunciation flags + FluencyScore, phoneme
  scores WITHOUT phoneme names. This is the everyday pass — scored against the
  accent model the user lives in.
- en-US: the only locale with phoneme NAMES (IPA), NBestPhonemes and
  ProsodyScore. Used ONLY to extract the L1-Spanish confusion targets; its
  General-American reference penalises legitimate British features (e.g.
  non-rhoticity), so never read the en-US pass as an overall score.

Requires AZURE_SPEECH_KEY + AZURE_SPEECH_REGION (expect 'uksouth').
Audio is uploaded to Azure; per Microsoft docs it is processed in memory and
not retained. Verified 2026-09-09 on the F0 free tier (scripts/azure-check.py):
scripted assessment, CompletenessScore, IPA phoneme names and ProsodyScore all
returned. Note the SDK nests scores under "PronunciationAssessment"; the REST
endpoint returns them flat — _aggregate reads the SDK shape.
"""
import json, os, threading

LOCALE = "en-US"   # see dual_locale_assessment: the only locale documented to return prosody AND
                   # named IPA phonemes. The user chose it outright on 2026-09-16.

# en-US IPA phonemes involved in the L1-Spanish confusion set
# (i:/ɪ, b/v, dʒ/j, θ/ð, schwa, word-final d/t for -ed endings, z/s).
# "iː" was added for the en-GB experiment and is kept: it costs nothing.
TARGET_PHONEMES = {"i", "iː", "ɪ", "b", "v", "d͡ʒ", "dʒ", "j", "θ", "ð", "ə", "z", "s", "d", "t"}

def _assess(wav, locale, phoneme_pass, reference_text=""):
    import azure.cognitiveservices.speech as speechsdk
    cfg = speechsdk.SpeechConfig(
        subscription=os.environ["AZURE_SPEECH_KEY"],
        region=os.environ["AZURE_SPEECH_REGION"])
    audio = speechsdk.audio.AudioConfig(filename=str(wav))
    pa = speechsdk.PronunciationAssessmentConfig(
        reference_text=reference_text or "",
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
        enable_miscue=bool(reference_text))   # scripted (read-aloud): omissions/insertions count
    if phoneme_pass:
        pa.phoneme_alphabet = "IPA"
        pa.nbest_phoneme_count = 3
        try:
            pa.enable_prosody_assessment()
        except Exception:
            pass  # prosody add-on may be unavailable on the free tier
    rec = speechsdk.SpeechRecognizer(speech_config=cfg, language=locale, audio_config=audio)
    pa.apply_to(rec)

    utterances, done = [], threading.Event()
    def on_recognized(evt):
        raw = evt.result.properties.get(
            speechsdk.PropertyId.SpeechServiceResponse_JsonResult)
        if raw:
            utterances.append(json.loads(raw))
    rec.recognized.connect(on_recognized)
    rec.session_stopped.connect(lambda evt: done.set())
    rec.canceled.connect(lambda evt: done.set())
    rec.start_continuous_recognition()
    done.wait(timeout=600)
    rec.stop_continuous_recognition()
    return utterances

def _aggregate(utterances, phoneme_pass):
    words, scores = [], {"AccuracyScore": [], "FluencyScore": [], "CompletenessScore": [], "ProsodyScore": [], "PronScore": []}
    weights = []
    for utt in utterances:
        best = (utt.get("NBest") or [{}])[0]
        ua = best.get("PronunciationAssessment", {})
        n = len(best.get("Words", []))
        if n:
            weights.append(n)
            for k in scores:
                if k in ua:
                    scores[k].append((ua[k], n))
        for w in best.get("Words", []):
            wa = w.get("PronunciationAssessment", {})
            entry = {"word": w.get("Word"), "accuracy": wa.get("AccuracyScore"),
                     "error": wa.get("ErrorType")}
            if phoneme_pass:
                phones = []
                for ph in w.get("Phonemes", []):
                    p = ph.get("PronunciationAssessment", {})
                    item = {"ph": ph.get("Phoneme"), "score": p.get("AccuracyScore")}
                    nbest = p.get("NBestPhonemes")
                    if nbest:
                        item["heard"] = [x.get("Phoneme") for x in nbest[:3]]
                    if (item["ph"] in TARGET_PHONEMES and (item["score"] or 100) < 60) \
                            or (item["score"] or 100) < 45:
                        phones.append(item)
                if phones:
                    entry["phonemes"] = phones
            words.append(entry)
    overall = {}
    for k, vals in scores.items():
        if vals:
            total = sum(n for _, n in vals)
            overall[k.lower().replace("score", "")] = round(sum(v * n for v, n in vals) / total, 1)
    flagged = [w for w in words
               if (w.get("error") not in (None, "None")) or (w.get("accuracy") or 100) < 60
               or w.get("phonemes")]
    return {"overall": overall, "flagged_words": flagged[:40], "word_count": len(words)}

def dual_locale_assessment(wav, reference_text=None, locale=LOCALE):
    """ONE en-US pass carrying the score, the IPA phonemes and prosody (2026-09-16).

    The locale is en-US because Microsoft's own documentation makes it the only one that works:
    prosody assessment "is only available in the en-US locale", the IPA phoneme alphabet is
    supported in en-US alone, and "only en-US provides phoneme name alongside scores. Other
    locales receive phoneme scores without names."

    That last line is not theory. Between 2026-09-14 and 2026-09-16 this ran as a single en-GB
    pass and every phoneme came back with an EMPTY name — 550 of them, against 0 in the records
    that still held an en-US pass — so the i/ii, schwa, s/z, cat/cut and j/y confusion classes
    silently lost their source, and with them the Minimal Pairs contrast weights that are
    computed from them. Azure did return a prosody number for en-GB, but for an undocumented
    locale, which is not something to measure a person against.

    The user chose en-US outright (2026-09-16): he lives in the UK now and may not later, and a
    US reference model was never the threat to him it would be to a British speaker — the
    objection raised on 09-14 was non-rhotic /r/ and the BATH/TRAP split, and as an L1-Spanish
    speaker he is rhotic and has neither.

    The key names `en_gb` and `en_us_targets` are kept: they are read by practice-review,
    practice-ingest, sayit and the Hub, and renaming them across a working pipeline buys nothing.
    `en_gb` means "the scoring pass"; `locale` inside it says which it actually was.

    With reference_text the pass runs SCRIPTED: accuracy is judged against the known words and
    CompletenessScore + Omission/Insertion errors become meaningful. Without it the assessment is
    unscripted — a rougher screen, but prosody is documented for both."""
    r = _aggregate(_assess(wav, locale, phoneme_pass=True, reference_text=reference_text), phoneme_pass=True)
    r["locale"] = locale
    return {
        "scripted": bool(reference_text),
        "locale": locale,
        "en_gb": r,
        "en_us_targets": {
            "overall_prosody": r["overall"].get("prosody"),
            "phoneme_findings": [w for w in r["flagged_words"] if w.get("phonemes")],
        },
        "note": f"{locale} is the score, the phonemes and the prosody — the only locale documented "
                f"to return all three (see the docstring)",
    }


def selftest():
    """Import-level checks only: the real assessment needs a key, audio and the SDK.

    This exists because on 2026-09-16 a bad edit left `locale=LOCALE` in the signature with no
    LOCALE defined, and every check in check.sh still passed — nothing imported this module, so a
    NameError sat in the hot path of the whole recording pipeline, undetected."""
    import inspect
    assert LOCALE == "en-US", LOCALE
    assert inspect.signature(dual_locale_assessment).parameters["locale"].default == LOCALE
    # one pass, not two: the second call was what blew the free tier on 2026-09-14
    src = inspect.getsource(dual_locale_assessment)
    assert src.count("_assess(") == 1, "the assessment must make exactly one pass: %d" % src.count("_assess(")
    assert TARGET_PHONEMES and all(isinstance(x, str) and x for x in TARGET_PHONEMES)
    for k in ("en_gb", "en_us_targets", "scripted", "locale", "note"):
        assert f'"{k}"' in src, f"callers read {k}; it must stay in the returned shape"
    assert "phoneme_pass=True" in src, "named IPA phonemes are the reason for this locale"
    print("azure_pa.py selftest: OK")
    return 0


if __name__ == "__main__":
    import sys
    # This module is a library — azure-check.py is the thing you run against the live service.
    if "--selftest" not in sys.argv:
        print("azure_pa.py is a library; use --selftest, or scripts/azure-check.py to test the service")
        sys.exit(2)
    sys.exit(selftest())
