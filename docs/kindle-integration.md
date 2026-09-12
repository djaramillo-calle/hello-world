# Claude ↔ Kindle Integration Landscape (August 2026)

Research report, agent-produced. Basis for the repo's Kindle bridge decisions.

## 0. The one fact that shapes everything

**Vocabulary Builder data exists only on the device.** Amazon does not sync
`vocab.db` to the cloud; `read.amazon.com/notebook` shows highlights/notes
only. No middleware (Readwise, Clippings.io) captures it — Readwise's own
blog suggests "highlight the word instead" as the workaround. So a
physical/USB path to `Kindle/system/vocabulary/vocab.db` is irreducible
unless the device is jailbroken. The repo's USB script is architecturally
correct, not a stopgap.

## 1. Landscape summary

| Approach | Data | Mechanism | State | Credential risk | Friction |
|---|---|---|---|---|---|
| **vocab.db over USB** (scripts/kindle-vocab.py; prior art: wzyboy/kindle_vocab_anki, prz3m/kind2anki, fluentcards) | Vocab lookups incl. usage sentence, book, timestamp | SQLite read of mounted device; WORDS/LOOKUPS/BOOK_INFO schema stable across firmware | Mature ecosystem; kind2anki updated 2025-08 | **None** | USB per sync |
| **Readwise Full + hosted MCP + Export API** | Highlights/notes only — NOT vocab | Their extension syncs the notebook from your logged-in browser; MCP via OAuth | Active, first-class | Low-moderate (no Amazon creds; data in Readwise cloud) | ~$120/yr, near-zero effort |
| **Claude in Chrome** on read.amazon.com | Highlights, library, currently-reading | Anthropic extension drives your own logged-in Chrome; visible actions, per-site permissions | First-party, GA on paid plans | **Low** | Semi-manual runs; DOM brittleness |
| Cookie-paste libs (Xetera/kindle-api) | Library, progress | Year-valid Amazon session cookies + TLS-spoofing proxy | Workaround-dependent | **High — refuse** | High |
| Community Kindle MCPs | Highlights fragments | File parsers / Playwright logins | Nothing production-grade in 2026 | Varies | High |
| Jailbreak + KUAL wireless sync | Everything, no USB | On-device scripts over Wi-Fi | Healthy ecosystem | No creds, but ToS/warranty exposure; update fragility | High setup |
| On-device Export Notes → email | One book's highlights | Official share feature | Official | None | Per-book, manual |
| Goodreads API | — | — | **Dead since Dec 2020** | — | — |

## 2. Ranked recommendations for this repo's architecture

1. **Keep and harden the USB vocab.db bridge** — the only vocab source,
   credential-free, already repo-shaped. Incremental by lookup id (done);
   optional friction fix: a udev/launchd/AutoHotkey watcher that runs the
   script automatically whenever the Kindle mounts, making "plug in to
   charge" = "synced". Card creation stays on the AnkiConnect MCP.
2. **Claude in Chrome for highlights + library** — free, credential-safe:
   site permission for read.amazon.com only; never export cookies to any
   third-party tool. A recurring local task walks the notebook and commits
   per-book Markdown to the repo.
3. **Readwise Full (~£8–10/mo)** — only if paying for zero-effort highlight
   sync is preferred; hosted MCP (OAuth) + Export API cron into the repo.
   Vendor-trust decision; still no vocab data.

## 3. Dead ends (do not revisit)

Goodreads API (closed 2020); any official Kindle read API (none exists;
Send to Kindle is push-only and tightening); cookie-paste tools (credential
posture to refuse); current community Kindle MCPs (0-star parsers or JP
Playwright logins, none touch vocab); Bookcision (absorbed, mobile copying
restricted late 2025); Clippings.io (manual, paid, no API); Snipd
(podcasts); scribe-sync (early-stage WebUSB, dominated by our script);
jailbreak wireless sync (works, but ToS/warranty/update fragility — file
under optional future experiment, eyes open).

## 4. Verification honesty

Egress blocks prevented reading readwise.io/docs.readwise.io/HN/glama
directly — Readwise MCP details come from search snippets and a 2026
third-party guide. Star counts and last-commit dates as rendered by GitHub.
Untested README claims flagged: l3a0 skill's truncation recovery;
scribe-sync's local-only claim; "schema varies by firmware" is anecdotal —
no documented breaking variant found.

*(Full source list in the session record; key links: wzyboy/kindle_vocab_anki,
prz3m/kind2anki, readwise.io/mcp, code.claude.com/docs/en/chrome,
kindlemodding.org.)*

## 5. Addendum 2026-08-30 — l3a0 kindle-highlights skill examined (HN 49424758)

Deep-read of github.com/l3a0/claude-plugins (the skill §4 flagged as
untested) plus its HN thread. Mechanism, previously uncatalogued here:
(1) JS scrape of the user's own read.amazon.com/notebook session via a
browser-control MCP; (2) character-precise highlight extents — including
export-hidden ones — from the Mac Kindle app's synced annotation SQLite
(com.amazon.Lassen, ksdk_annotation_v1.db); (3) Cloud Reader page canvases
OCR'd locally (Apple Vision), cut to the known extents by position
arithmetic. No DRM decryption anywhere; recovery figures (815/815
export-blocked recovered, 0–2 char residuals) are the author's own,
self-reported. Shipped code reads clean (no third-party endpoints, no
credential handling, no injection-style SKILL.md instructions).

**Verdict: reject the mechanism, adopt the signal.** Rejection factors:
automated scraping of a logged-in Amazon session and deliberate defeat of
the publisher clipping allowance collide with this doc's no-credential/
no-ToS bar; the prerequisite "Allow JavaScript from Apple Events" Chrome
setting is a machine-wide downgrade its docs never revert; repo is a week
old, single-author, flagged submission on HN; and the pipeline needs the
Mac Kindle app + Cloud Reader (already failing for newer titles per
commenters), not the physical device this project reads on.

**Gap this exposed in §2's landscape table: `documents/My Clippings.txt`**
— the device's own plain-text highlight log, readable over the SAME USB
mount as vocab.db, zero credentials, zero scraping. Highlights are a
complementary harvest channel to lookups (deliberately-chosen multi-word
chunks — exactly the phrasal-verb/collocation material the observation
log hunts — vs involuntary single-word gaps). Plan: a
scripts/kindle-highlights.py mirroring kindle-vocab.py conventions
(dedupe/supersede edited-highlight duplicates, flag clipping-limit
truncations, carded flags, shared 25-cards/week cap). Known limits:
device-made highlights only; per-book clipping cap can truncate text on
DRM titles; deletions on-device never remove records. Highlight counts
are engagement data, never a metric — nothing here feeds tracking.tsv.
For full-book highlight ARCHIVAL (the problem l3a0's skill actually
solves) the fallback remains §2's Claude-in-Chrome notebook route, not
the third-party skill.
