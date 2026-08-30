# Project: Adult English — diagnosis, routine, and tracking

The user is an adult English learner (L1 Spanish, UK-based, office job
09:30–17:00 UK time, gym 18:15 most weekdays). Goal: conversational,
real-world English. Key artifacts:

- `diagnostic.html` — English Signal Check battery (form v2, post-audit).
  Re-run every 5 weeks; one row appended to `tracking.tsv` per run.
- `routine.html` — English Runbook (daily plan; focus dial, 2-conversation
  weekly floor, no work missions — removed at user request 2026-08-30).
- `docs/plan/final-plan.md` — the adjudicated plan. Its cardinal rule:
  **at most ONE plan lever changes per 5-week cycle**, and only at the
  diagnostic week-close, and only when the current dial's target metric
  missed its noise threshold.
- `docs/METHOD.md` — instrument spec, noise thresholds, form history.
- `observations.md` — the chat-based English observation log (see below).

## Standing instruction: maintain the observation log

In every session with this user, passively note their English in their own
messages and maintain `observations.md`:

1. **Harvest, don't correct.** No unsolicited mid-chat corrections or
   rewrites of the user's sentences. Digest on request or at the weekly
   review only. Exception: if the user declares "English mode" in a chat,
   switch to prompt-style feedback (signal the breakdown, let them repair —
   never reformulate for them).
2. **Pattern discipline.** One occurrence = `WATCHING` (presumed typo).
   Two or more independent occurrences = `PATTERN` (append entry + suggest
   production-format SRS cards). No recurrence across ~4 weeks = `RETIRED`.
3. **What to watch** (from the baseline entries): article omission before
   abstract nouns; phrasal-verb avoidance / Latinate monoculture;
   subject–verb agreement; countability; collocation (also log strengths).
4. **Register honesty.** Chat is written, self-paced, technical. Never
   infer speaking ability from it, and never turn this log into a number —
   nothing from it goes into `tracking.tsv`.
5. **Adjustment gate.** Log findings may *recommend* plan changes any time,
   but plan changes are *implemented* only under the final plan's
   one-lever-per-cycle rule at a diagnostic week-close. Card and
   crutch-word-list additions are exempt (they are harvest, not levers).

A weekly Routine ("Weekly English observation review", Fridays ~18:00 UTC)
fires into the long-running session to write the digest. If working in a
fresh session, append observations with dated entries in the established
format and commit with message prefix "observations:".

## Anki (local sessions only)

The user's SRS lives in desktop Anki, controlled via an Anki MCP server +
AnkiConnect on their local machine. Cloud sessions cannot reach it; git is
the bridge. Conventions for any LOCAL session with the Anki MCP attached:

- Deck name: **English Runbook**. Card format: production — front = cue
  ("Say it: ...", "Complete aloud: ...", "Phrasal (instead of X): ..."),
  back = the target chunk. The user says the answer ALOUD before flipping.
- Seed deck: `seed-deck.csv` (33 cards). Import it once via MCP on first
  setup; thereafter add cards directly from `observations.md` suggestions
  and conversation harvests. Cap ~25 new cards/week; deck cap ~120 live.
- **Stats export (feeds the cloud Friday review):** when working locally,
  export a compact summary to `logs/anki-stats.json` — date, reviews done
  per day since last export, mature/young/new counts, cards with lapses
  ≥4 (leech candidates) — commit and push ("observations: anki stats").
  The weekly Routine reads this file from git; without it, the review
  evaluates chat patterns only.
- Adjustments (suspend leeches, reformulate cards, retire RETIRED-status
  patterns' cards) are harvest-level actions: allowed any time, no
  one-lever gate. Never change the scheduler settings without the user.

## Kindle (local sessions only)

Kindle has no API; the e-reader's Vocabulary Builder database is the
bridge. When the user plugs the Kindle in during a local session:

- Run `python3 scripts/kindle-vocab.py <kindle>/system/vocabulary/vocab.db`.
  It merges new lookups (word + usage sentence + book) into
  `logs/kindle-vocab.json`, deduplicated and idempotent.
- Turn the best new lookups into production cards in the English Runbook
  deck — front = the user's own usage sentence with the word blanked, said
  aloud — respecting the 25-new-cards/week cap (Kindle + chat harvests
  share the cap). Mark used entries `"carded": true`. Commit with prefix
  "observations:". The cloud Friday review reads this file from git.
- Lookups are harvest, never a metric: frequency of dictionary lookups is
  reading-difficulty data, not a proficiency score.

## Repo conventions

- Branch: `claude/adult-language-learning-gnk7i1`. Commit and push after
  meaningful changes; no PRs unless asked.
- `diagnostic.html` and `routine.html` are standalone pages (full head).
  Their published artifacts are wrapper-stripped copies — republish via the
  existing artifact URLs, never as new artifacts.
- Tests: `node scripts/test.js` (jsdom; non-zero exit on failure). Run
  before committing any change to `diagnostic.html`. Changing items,
  scoring keys, wordlists, or thresholds is COMPARABILITY-BREAKING: bump
  the form version in `docs/METHOD.md` and warn the user that tracking
  history resets.
