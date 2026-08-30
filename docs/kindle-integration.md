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
