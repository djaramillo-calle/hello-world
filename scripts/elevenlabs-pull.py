#!/usr/bin/env python3
"""Optional upgrade path for AI conversations: pull finished conversations from
an ElevenLabs Agents agent (real ASR, per-turn offsets, agent-side error
extraction) into git, and count them as AI conversations in the hub day docs.

    ELEVENLABS_API_KEY=... ELEVENLABS_AGENT_ID=... python3 scripts/elevenlabs-pull.py
    python3 scripts/elevenlabs-pull.py --selftest

Outputs:
  logs/ai-sessions/<conversation_id>.json   the conversation object (transcript, metadata, analysis)
  logs/ai-sessions/state.json               {"after": <unix>} for incremental pulls
  logs/hub/days.json                        conversations.ai += 1, talk_min += duration (idempotent by id)

Skips silently when the env vars are absent, so coach-sync can call it
unconditionally. The API shape (GET /v1/convai/conversations, GET
/v1/convai/conversations/{id}) was verified against the elevenlabs-python
types on 2026-09-09 but NOT against a live account — the first real run
should be watched. Transcripts are harvest for the observation log; nothing
here is a proficiency score.
"""
import datetime as dt, json, os, pathlib, sys, urllib.request, urllib.parse

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "logs" / "ai-sessions"
HUB = REPO / "logs" / "hub" / "days.json"
BASE = "https://api.elevenlabs.io"

def api(path, key, params=None):
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    req = urllib.request.Request(f"{BASE}{path}{q}", headers={"xi-api-key": key, "User-Agent": "english-runbook/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def list_conversations(key, agent_id, after):
    out, cursor = [], None
    while True:
        params = {"agent_id": agent_id, "page_size": 100}
        if after: params["call_start_after_unix"] = int(after)
        if cursor: params["cursor"] = cursor
        page = api("/v1/convai/conversations", key, params)
        out.extend(page.get("conversations", []))
        cursor = page.get("next_cursor")
        if not page.get("has_more") or not cursor:
            return out

def summarise(conv):
    """Compact learner-side telemetry from a conversation object."""
    tr = conv.get("transcript") or []
    meta = conv.get("metadata") or {}
    user = [t for t in tr if t.get("role") == "user" and t.get("message")]
    words = sum(len(str(t["message"]).split()) for t in user)
    start = meta.get("start_time_unix_secs")
    started = dt.datetime.fromtimestamp(start, dt.timezone.utc).isoformat().replace("+00:00", "Z") if start else None
    analysis = conv.get("analysis") or {}
    dc = analysis.get("data_collection_results") or {}
    errors = None
    if "learner_errors" in dc:
        try: errors = json.loads(dc["learner_errors"].get("value") or "[]")
        except (ValueError, AttributeError): errors = dc["learner_errors"].get("value")
    return {"id": conv.get("conversation_id"), "kind": "ai-elevenlabs", "started": started,
            "duration_s": meta.get("call_duration_secs"), "learner_turns": len(user), "learner_words": words,
            "agent_turns": sum(1 for t in tr if t.get("role") == "agent"), "summary": analysis.get("transcript_summary"),
            "errors": errors, "evaluation": {k: (v or {}).get("result") for k, v in (analysis.get("evaluation_criteria_results") or {}).items()}}

def fold_into_hub(summaries, hub_path=HUB):
    try: hub = json.loads(hub_path.read_text(encoding="utf-8"))
    except (OSError, ValueError): hub = {}
    added = 0
    for s in summaries:
        if not s.get("started"): continue
        try: local = dt.datetime.fromisoformat(s["started"].replace("Z", "+00:00")).astimezone().date().isoformat()
        except ValueError: continue
        d = hub.setdefault(local, {"date": local})
        ids = d.setdefault("ai_session_ids", [])
        if s["id"] in ids: continue
        ids.append(s["id"]); added += 1
        c = d.setdefault("conversations", {}); c["ai"] = int(c.get("ai") or 0) + 1
        d["talk_min"] = int(d.get("talk_min") or 0) + round((s.get("duration_s") or 0) / 60)
        d["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if added:
        hub_path.parent.mkdir(parents=True, exist_ok=True)
        hub_path.write_text(json.dumps(dict(sorted(hub.items())), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return added

def selftest():
    import tempfile
    conv = {"agent_id": "a", "conversation_id": "conv_1", "status": "done",
            "transcript": [{"role": "agent", "message": "What did you do at the weekend?", "time_in_call_secs": 0},
                           {"role": "user", "message": "I go to gym and after I meet with friend.", "time_in_call_secs": 4},
                           {"role": "agent", "message": "Sorry, what do you mean?", "time_in_call_secs": 9},
                           {"role": "user", "message": "I went to the gym and then I met a friend.", "time_in_call_secs": 12}],
            "metadata": {"start_time_unix_secs": 1757954400, "call_duration_secs": 612},
            "analysis": {"transcript_summary": "weekend", "evaluation_criteria_results": {"learner_repaired_after_prompt": {"result": "success"}},
                         "data_collection_results": {"learner_errors": {"value": "[{\"utterance\":\"I go to gym\",\"issue\":\"past tense / article\",\"category\":\"grammar\"}]"}}}}
    s = summarise(conv)
    assert s["learner_turns"] == 2 and s["learner_words"] == 21 and s["errors"][0]["issue"].startswith("past") and s["evaluation"]["learner_repaired_after_prompt"] == "success", s
    with tempfile.TemporaryDirectory() as td:
        hub = pathlib.Path(td) / "days.json"
        assert fold_into_hub([s], hub) == 1
        assert fold_into_hub([s], hub) == 0, "idempotent by conversation id"
        d = json.loads(hub.read_text()); day = next(iter(d.values()))
        assert day["conversations"]["ai"] == 1 and day["talk_min"] == 10, day
    print("elevenlabs-pull.py selftest: OK")

def main():
    if "--selftest" in sys.argv: return selftest()
    key, agent = os.environ.get("ELEVENLABS_API_KEY"), os.environ.get("ELEVENLABS_AGENT_ID")
    if not key or not agent:
        print("elevenlabs: ELEVENLABS_API_KEY/ELEVENLABS_AGENT_ID not set — skipped"); return
    OUT.mkdir(parents=True, exist_ok=True)
    sp = OUT / "state.json"
    after = json.loads(sp.read_text()).get("after") if sp.exists() else None
    convs = [c for c in list_conversations(key, agent, after) if c.get("status") in (None, "done")]
    summaries, newest = [], after or 0
    for c in convs:
        cid = c.get("conversation_id")
        p = OUT / f"{cid}.json"
        if not cid or p.exists(): continue
        full = api(f"/v1/convai/conversations/{cid}", key)
        p.write_text(json.dumps(full, indent=1, ensure_ascii=False), encoding="utf-8")
        s = summarise(full); summaries.append(s)
        newest = max(newest, (full.get("metadata") or {}).get("start_time_unix_secs") or 0)
    added = fold_into_hub(summaries)
    if newest: sp.write_text(json.dumps({"after": newest}) + "\n")
    print(f"elevenlabs: {len(summaries)} new conversation(s), {added} folded into hub days")

if __name__ == "__main__":
    main()
