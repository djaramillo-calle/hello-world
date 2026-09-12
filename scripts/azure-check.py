#!/usr/bin/env python3
"""Azure Speech first-run check — no SDK, no microphone, stock python3.

    AZURE_SPEECH_KEY=... AZURE_SPEECH_REGION=uksouth python3 scripts/azure-check.py
    python3 scripts/azure-check.py --selftest

Answers the three first-run questions from docs/PRACTICE.md on the tier you
actually have (F0 free or paid):
  1. does the key + region work at all (token endpoint)?
  2. does pronunciation assessment work in SCRIPTED mode (reference text,
     miscues, CompletenessScore) on en-GB — the real score for read-alouds?
  3. does the en-US phoneme pass return IPA phoneme names and a ProsodyScore
     (prosody may need the paid tier)?

It synthesises one sentence with Azure's own TTS (free tier includes it),
sends that WAV back to the assessment REST endpoint, and prints the verdict.
Writes logs/azure-check.json (scores and capability flags, never the key).
Also runs in the cloud when the two variables are environment variables there.
"""
import base64, datetime as dt, json, os, pathlib, sys, urllib.error, urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "logs" / "azure-check.json"
UA = "english-runbook/1.0"
SENTENCE = "On Thursday I usually go to the gym after work, and then I read for half an hour."
# deliberately not the anchor passage: the check must never write a row into the pronunciation ledger

def _req(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def token(region, key):
    st, body = _req(f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken",
                    data=b"", headers={"Ocp-Apim-Subscription-Key": key}, method="POST")
    return st, body.decode("utf-8", "replace")[:200]

def synthesise(region, key, text, voice="en-GB-SoniaNeural"):
    ssml = (f"<speak version='1.0' xml:lang='en-GB'><voice name='{voice}'>"
            f"<prosody rate='-5%'>{text}</prosody></voice></speak>").encode("utf-8")
    st, body = _req(f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1", data=ssml, method="POST",
                    headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                             "X-Microsoft-OutputFormat": "riff-16khz-16bit-mono-pcm"})
    return st, body

def assess(region, key, wav, locale, reference, prosody, ipa):
    pa = {"ReferenceText": reference or "", "GradingSystem": "HundredMark", "Granularity": "Phoneme",
          "Dimension": "Comprehensive", "EnableMiscue": bool(reference)}
    if ipa: pa.update({"PhonemeAlphabet": "IPA", "NBestPhonemeCount": 3})
    if prosody: pa["EnableProsodyAssessment"] = True
    hdr = base64.b64encode(json.dumps(pa).encode()).decode()
    url = f"https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language={locale}&format=detailed"
    st, body = _req(url, data=wav, method="POST",
                    headers={"Ocp-Apim-Subscription-Key": key, "Accept": "application/json",
                             "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
                             "Pronunciation-Assessment": hdr})
    try: return st, json.loads(body)
    except ValueError: return st, {"raw": body.decode("utf-8", "replace")[:300]}

def summarise(resp):
    """Pull the capability facts out of one detailed-format response."""
    out = {"status": resp.get("RecognitionStatus"), "scores": {}, "words": 0, "miscues": 0, "phoneme_names": False, "prosody": False}
    nb = (resp.get("NBest") or [{}])[0]
    # the REST short-audio endpoint returns the scores flat on the NBest item; the SDK nests them under PronunciationAssessment
    pa = {**nb, **(nb.get("PronunciationAssessment") or {})}
    for k in ("AccuracyScore", "FluencyScore", "CompletenessScore", "ProsodyScore", "PronScore"):
        if k in pa: out["scores"][k] = pa[k]
    out["prosody"] = "ProsodyScore" in pa
    out["nbest_keys"] = sorted(k for k in nb if k != "Words")
    for w in nb.get("Words") or []:
        out["words"] += 1
        wpa = {**w, **(w.get("PronunciationAssessment") or {})}
        if wpa.get("ErrorType") not in (None, "None"): out["miscues"] += 1
        for ph in w.get("Phonemes") or []:
            if ph.get("Phoneme"): out["phoneme_names"] = True
    out["text"] = nb.get("Display") or nb.get("Lexical")
    return out

def run(region, key):
    report = {"checked": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "region": region, "steps": {}}
    st, msg = token(region, key)
    report["steps"]["token"] = {"http": st}
    if st != 200:
        report["verdict"] = f"key/region rejected by the token endpoint (HTTP {st}: {msg}). Check the key, and that the region is the resource's region (e.g. uksouth)."
        return report
    st, wav = synthesise(region, key, SENTENCE)
    report["steps"]["tts"] = {"http": st, "bytes": len(wav)}
    if st != 200 or len(wav) < 1000:
        report["verdict"] = f"token OK but text-to-speech failed (HTTP {st}: {wav[:200]!r}). The Speech resource may still be provisioning — retry in a minute."
        return report
    st, gb = assess(region, key, wav, "en-GB", SENTENCE, prosody=False, ipa=False)
    report["steps"]["en_gb_scripted"] = {"http": st, **(summarise(gb) if st == 200 else {"error": gb})}
    st, us = assess(region, key, wav, "en-US", SENTENCE, prosody=True, ipa=True)
    report["steps"]["en_us_phoneme_prosody"] = {"http": st, **(summarise(us) if st == 200 else {"error": us})}
    g, u = report["steps"]["en_gb_scripted"], report["steps"]["en_us_phoneme_prosody"]
    report["capabilities"] = {
        "assessment": g.get("http") == 200 and g.get("status") == "Success" and bool(g.get("scores")),
        "completeness": "CompletenessScore" in (g.get("scores") or {}),
        "phoneme_names": bool(u.get("phoneme_names")),
        "prosody": bool(u.get("prosody")),
    }
    c = report["capabilities"]
    report["verdict"] = ("assessment " + ("OK" if c["assessment"] else "FAILED") +
                         " · scripted completeness " + ("OK" if c["completeness"] else "missing") +
                         " · IPA phonemes " + ("OK" if c["phoneme_names"] else "missing") +
                         " · prosody " + ("OK" if c["prosody"] else "not available on this tier (fine: prosody is optional)"))
    return report

def selftest():
    resp = {"RecognitionStatus": "Success", "NBest": [{"Display": "On Thursday I go.", "PronunciationAssessment": {
        "AccuracyScore": 91.0, "FluencyScore": 88.0, "CompletenessScore": 100.0, "PronScore": 90.0, "ProsodyScore": 77.0},
        "Words": [{"Word": "on", "PronunciationAssessment": {"ErrorType": "None"}, "Phonemes": [{"Phoneme": "ɒ"}]},
                  {"Word": "thursday", "PronunciationAssessment": {"ErrorType": "Mispronunciation"}, "Phonemes": [{"Phoneme": "θ"}]}]}]}
    s = summarise(resp)
    assert s["scores"]["CompletenessScore"] == 100.0 and s["prosody"] and s["phoneme_names"] and s["miscues"] == 1 and s["words"] == 2, s
    flat = {"RecognitionStatus": "Success", "NBest": [{"Display": "On Thursday I go.", "AccuracyScore": 95.0, "FluencyScore": 90.0,
            "CompletenessScore": 100.0, "PronScore": 93.0, "Words": [{"Word": "thursday", "AccuracyScore": 40.0, "ErrorType": "Mispronunciation", "Phonemes": [{"Phoneme": "θ"}]}]}]}
    s3 = summarise(flat)   # REST shape
    assert s3["scores"]["CompletenessScore"] == 100.0 and s3["miscues"] == 1 and s3["phoneme_names"] and not s3["prosody"], s3
    s2 = summarise({"RecognitionStatus": "NoMatch"})
    assert s2["status"] == "NoMatch" and not s2["scores"] and not s2["prosody"], s2
    print("azure-check.py selftest: OK")

def main():
    if "--selftest" in sys.argv: return selftest()
    key, region = os.environ.get("AZURE_SPEECH_KEY"), os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        print("azure-check: AZURE_SPEECH_KEY / AZURE_SPEECH_REGION not set — nothing to check"); return 2
    report = run(region.strip().lower(), key.strip())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    for k, v in report["steps"].items():
        print(f"{k:24s} " + ", ".join(f"{a}={b}" for a, b in v.items() if a != "error") + (f"  error={str(v['error'])[:160]}" if v.get("error") else ""))
    print("verdict:", report["verdict"])
    print(f"written: {OUT.relative_to(REPO)}")
    return 0 if report.get("capabilities", {}).get("assessment") else 1

if __name__ == "__main__":
    sys.exit(main())
