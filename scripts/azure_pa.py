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
not retained. First-run checks (free F0 tier): confirm assessment returns
results at all, and whether prosody works or needs the paid tier.
"""
import json, os, threading

# en-US IPA phonemes involved in the L1-Spanish confusion set
# (i:/ɪ, b/v, dʒ/j, θ/ð, schwa, word-final d/t for -ed endings, z/s)
TARGET_PHONEMES = {"i", "ɪ", "b", "v", "d͡ʒ", "dʒ", "j", "θ", "ð", "ə", "z", "s", "d", "t"}

def _assess(wav, locale, phoneme_pass):
    import azure.cognitiveservices.speech as speechsdk
    cfg = speechsdk.SpeechConfig(
        subscription=os.environ["AZURE_SPEECH_KEY"],
        region=os.environ["AZURE_SPEECH_REGION"])
    audio = speechsdk.audio.AudioConfig(filename=str(wav))
    pa = speechsdk.PronunciationAssessmentConfig(
        reference_text="",
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
        enable_miscue=False)
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
    words, scores = [], {"AccuracyScore": [], "FluencyScore": [], "ProsodyScore": [], "PronScore": []}
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

def dual_locale_assessment(wav):
    """en-GB everyday pass + en-US phoneme-target pass. Serial (free tier concurrency = 1)."""
    gb = _aggregate(_assess(wav, "en-GB", phoneme_pass=False), phoneme_pass=False)
    us = _aggregate(_assess(wav, "en-US", phoneme_pass=True), phoneme_pass=True)
    return {
        "en_gb": gb,
        "en_us_targets": {
            "overall_prosody": us["overall"].get("prosody"),
            "phoneme_findings": [w for w in us["flagged_words"] if w.get("phonemes")],
        },
        "note": "en-GB is the score; en-US pass is only for phoneme identities (US reference model)",
    }
