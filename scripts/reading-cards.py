#!/usr/bin/env python3
"""Dictionary lookups → production cards, mechanically.

    python3 scripts/reading-cards.py [--max N]     # default 5 per run; queues into cards/queue.tsv, marks lookups carded
    python3 scripts/reading-cards.py --selftest

Runs on the Mac (coach-sync, before anki-push-cards.py) and in the cloud (daily Routine) — idempotent:
a lookup is used once (`carded: true` in logs/reading/vocab.json), the queue dedupes by front, and the
25-new-cards-per-week cap is enforced where cards enter Anki (anki-push-cards.py), not here.

Card shape (CLAUDE.md, Kindle/reading rules): the learner's OWN sentence with the word blanked, said
aloud, then flipped — front "Complete aloud: … ____ …  (c…, 14 letters)", back the word and the full
sentence. Newest lookups first; a lookup without a usable sentence (fewer than 6 words, or not containing
the word) is skipped, never invented.
"""
import datetime as dt, importlib.util, json, pathlib, re, sys

REPO = pathlib.Path(__file__).resolve().parent.parent
VOCAB = REPO / "logs" / "reading" / "vocab.json"
WINDOW = 14   # words kept on each side of the blank
BACKLOG = 25  # stop queueing while this many cards already wait: the Anki push takes 25 a WEEK and this
              # script runs on every sync (~3x a day), so without the brake the queue grows without bound
              # and a lookup is spent on a card that only reaches the deck weeks later. Lookups are left
              # un-carded instead, so the newest-first pick stays fresh when room opens up.

def _pr():
    spec = importlib.util.spec_from_file_location("practice_review", REPO / "scripts" / "practice-review.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def blank(usage, word):
    """The sentence with the word blanked (all inflections of the same stem), trimmed to a window around it."""
    words = usage.split()
    rx = re.compile(r"^\W*" + re.escape(word[:max(4, len(word) - 2)]), re.I)
    hits = [i for i, w in enumerate(words) if rx.match(w)]
    if not hits: return None
    i = hits[0]
    lo, hi = max(0, i - WINDOW), min(len(words), i + WINDOW + 1)
    out = ["____" if rx.match(w) else w for w in words[lo:hi]]
    s = " ".join(out)
    if lo > 0: s = "… " + s
    if hi < len(words): s = s + " …"
    return s

def make_card(e):
    word, usage = (e.get("word") or "").strip(), (e.get("usage") or "").strip()
    if len(word) < 3 or len(usage.split()) < 6: return None
    b = blank(usage, word)
    if not b: return None
    return {"front": f"Complete aloud: {b}  ({word[0]}…, {len(word)} letters)",
            "back": f"{word} — {usage}" + (f"  [{e.get('book')}]" if e.get("book") and e.get("book") != "unknown" else "")}

def build(vocab, max_cards=5):
    """Cards for the newest un-carded lookups; returns (cards, entries used)."""
    cands = sorted((x for x in vocab.get("lookups") or [] if not x.get("carded")), key=lambda x: x.get("ts") or 0, reverse=True)
    cards, used = [], []
    for e in cands:
        c = make_card(e)
        if not c: continue
        cards.append(c); used.append(e)
        if len(cards) >= max_cards: break
    return cards, used

def backlog(pr, queue_path=None):
    return sum(1 for r in pr.load_queue(queue_path or pr.QUEUE) if r.get("status") == "queued")

# Say-it took the reading lookups over on 2026-09-15, at the user's decision. A new word is one he
# has never SAID, and a card he reads silently teaches the meaning while telling him nothing about
# the mouth; the drill plays a model and scores the attempt. Carding them here as well would double
# a daily load against an Anki cap that is already full and a deck with no reviews in sixty days.
# Nothing is deleted: the cards queued before that date still go up as room opens, and `carded` is
# still the shared flag, now set by sayit.py instead.
LOOKUPS_GO_TO_SAYIT = True

def run(vocab_path=VOCAB, queue_path=None, max_cards=5, now=None, backlog_cap=BACKLOG,
        lookups_to_sayit=LOOKUPS_GO_TO_SAYIT):
    if lookups_to_sayit: return 0, 0
    pr = _pr()
    waiting = backlog(pr, queue_path)
    if backlog_cap and waiting >= backlog_cap: return 0, 0
    if backlog_cap: max_cards = min(max_cards, backlog_cap - waiting)
    try: vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return 0, 0
    cards, used = build(vocab, max_cards)
    if not cards: return 0, 0
    added = pr.queue_cards(cards, source="reading", kind="lookup", tags=["reading", "production"], path=queue_path or pr.QUEUE, now=now)
    for e in used: e["carded"] = True
    vocab_path.write_text(json.dumps(vocab, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return added, len(used)

def selftest():
    import tempfile
    e = {"word": "spurious", "usage": "mere process of disintegration has become an irresistible temptation, not only because it has assumed the spurious grandeur of “historical necessity,” but also because everything outside it has begun to appear lifeless", "book": "The Origins of Totalitarianism", "ts": 2}
    c = make_card(e)
    assert c["front"].startswith("Complete aloud: … ") and " ____ grandeur" in c["front"] and c["front"].endswith("(s…, 8 letters)"), c["front"]
    assert c["back"].startswith("spurious — mere process") and c["back"].endswith("[The Origins of Totalitarianism]"), c["back"]
    assert make_card({"word": "old", "usage": "", "ts": 1}) is None and make_card({"word": "respite", "usage": "no respite", "ts": 1}) is None
    assert blank("The vanquished were many.", "vanquish") == "The ____ were many."      # stem match covers inflections
    assert blank("Nothing here.", "respite") is None
    vocab = {"lookups": [e, {"word": "grandeur", "usage": e["usage"], "book": "x", "ts": 3}, {"word": "conglomeration", "usage": "a b c d e f conglomeration g", "ts": 1, "carded": True}]}
    cards, used = build(vocab, 5)
    assert [u["word"] for u in used] == ["grandeur", "spurious"], [u["word"] for u in used]   # newest first, carded skipped
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td); vp = td / "vocab.json"; vp.write_text(json.dumps(vocab)); q = td / "queue.tsv"
        assert run(vp, q, 1, now="2026-09-10T12:00:00Z", lookups_to_sayit=False) == (1, 1)
        assert run(vp, q, 5, now="2026-09-10T12:00:00Z", lookups_to_sayit=False) == (1, 1), "second run takes the remaining one only"
        assert run(vp, q, 5, lookups_to_sayit=False) == (0, 0)
        assert run(vp, q, 5, lookups_to_sayit=True) == (0, 0), "handed to Say it: this script cards no lookups"
        v2 = json.loads(vp.read_text()); assert all(x["carded"] for x in v2["lookups"])
        rows = [l for l in q.read_text().splitlines() if l and not l.startswith("#")]
        assert len(rows) == 3 and rows[1].split("\t")[3] == "lookup" and rows[1].split("\t")[7] == "queued", rows
    # the brake: a queue already at the cap takes nothing, and a nearly-full one takes only the room left
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td); vp = td / "vocab.json"; q = td / "queue.tsv"
        # distinct sentences: identical fronts would collapse under the queue's dedupe and hide the brake
        many = {"lookups": [{"word": f"wording{i}", "usage": f"the {i} quiet morning after a long wording{i} of the night", "ts": i} for i in range(9)]}
        vp.write_text(json.dumps(many))
        assert run(vp, q, 5, now="2026-09-10T12:00:00Z", backlog_cap=3, lookups_to_sayit=False) == (3, 3), "fills only the room left"
        assert run(vp, q, 5, now="2026-09-10T12:00:00Z", backlog_cap=3, lookups_to_sayit=False) == (0, 0), "at the cap: nothing"
        assert sum(1 for x in json.loads(vp.read_text())["lookups"] if x.get("carded")) == 3, "un-picked lookups stay available"
    print("reading-cards.py selftest: OK")

def main():
    if "--selftest" in sys.argv: return selftest()
    n = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 5
    added, used = run(max_cards=n)
    waiting = backlog(_pr())
    if used: print(f"reading-cards: {added} queued from {used} lookups ({waiting} waiting)")
    elif LOOKUPS_GO_TO_SAYIT:
        print(f"reading-cards: new lookups go to Say it since 2026-09-15 — none carded ({waiting} queued earlier still waiting)")
    elif waiting >= BACKLOG: print(f"reading-cards: {waiting} cards already waiting (cap {BACKLOG}) — no new lookups carded")
    else: print("reading-cards: nothing new to card")
    return 0

if __name__ == "__main__":
    sys.exit(main())
