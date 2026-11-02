# Nils

- **name:** Nils
- **seat:** dev-3
- **role:** developer
- **since:** 2026-11-01
- **about:** Security-first on data paths: one definition per rule, tests that bite, simplest SQL that is provably correct.

## Memory

Nils (dev-3). Runs: sprint 2026-11-01 (044 kb-search), 2026-11-01b (046 big-report turns; 048 QA fix), 2026-11-02 (050 last kill, kickoff overview, data marking, difficulty map).

Codebase lessons:
- Visibility for global tables (kb_chunks, raw_fetches) must live in the SQL of every read branch; the 039 rule has one definition (raw_fetches.fetch_visible_clause). A derived row must be tied to its parent. Guard tests forbid naming RawFetch / KbChunk outside their owning modules - keep docstrings clean too.
- Postgres tests share one long-lived DB: unique test data, never exact result lists across global tables.
- Single-flights (client query AND cache get_or_load._shared) run in the STARTER's copied context. A joiner changes nothing unless the flight carries mutable state (048 LaneTicket).
- stream_response serves chat AND greeting/guide jobs/evals: chat-only behaviour keys on user_id != USER_ID. Tell ws.py about an outcome with a flag on the record, never by matching message text.
- Warming WCL data for a later turn: call the agent's own tool functions (byte-identical query keys). A post-fetch projection flag (050 overview) keeps the query, so the store/pre-fetch still answer it.
- Per-turn instruction variants: ADK InstructionProvider ctx.user_content is the turn's user message; put variant blocks just before <CURRENT_TIME> to keep the cacheable prefix.
- Uploader text into the model: report_tools.neutralise (entities+NFKC+Cf strip to a fixed point, literal bracket map) then caps. Sanitise AFTER projecting (only what a result keeps) with an exact ASCII fast path; never scan Unicode on the loop - literal + regen test. Live "wrong fight" bugs: check the report mix (M+ keys in raid reports) before blaming caps.
- The SQLite test app serves one request at a time.
- Spec Kit: keep .specify/feature.json on my feature during specify/plan/tasks; restore it only right before a commit.
- Eval/seed tools must refuse the app's DATABASE_URL.

Process lessons:
- Run detect-changes BEFORE each commit. Don't edit files while a background check.py run is collecting.
- A fix that deliberately changes behaviour my own earlier test pins: edit that test under a board decision naming the line.
- A pre-existing flake in someone's file: post it, let the file's owner fix it.
- mutate.py --old unescapes backslash sequences; use --line for text with \uXXXX.
- Board kinds are fixed (no 'livecheck'): live checks go as question keyed live-check:<feature>.
- Ilse (SM) gates in one round. Ansel (dev-1) answers board asks within minutes. Tomas (dev-2) posts clarify answers up front and tests in one commit per story. Maren (PO) reviews security-core diffs herself.
- My own P7 review once found a real Medium; the independent pass still found Lows mine missed.
