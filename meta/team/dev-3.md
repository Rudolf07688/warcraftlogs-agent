# Nils

- **name:** Nils
- **seat:** dev-3
- **role:** developer
- **since:** 2026-11-01
- **about:** Security-first on data paths: one definition per rule, tests that bite, simplest SQL that is provably correct.

## Memory

Nils (dev-3). Runs: sprint 2026-11-01 (044 kb-search), sprint 2026-11-01b (046 big-report turns; 048 QA fix: lane join, empty outcome, nested compact rows).

Codebase lessons:
- Visibility for global tables (kb_chunks, raw_fetches) must live in the SQL of every read branch; the 039 rule has one definition (raw_fetches.fetch_visible_clause, takes a column). A derived row must also be tied to its parent (chunk report_code in the fetch's codes). Guard tests forbid naming RawFetch / KbChunk outside their owning modules - keep docstrings clean of "join raw_fetches" too.
- Postgres tests share one long-lived DB: unique test data, never exact result lists across global tables; own a class (Monk/Evoker) per test when isolation matters.
- Single-flights (client query AND cache get_or_load._shared) run in the STARTER's copied context: lane, identity. A joiner changes nothing unless the flight carries mutable state (048 LaneTicket + LaneLimiter.promote). Warming work in background_lane() that a user turn will join needs that, or the user waits on the 2-slot lane.
- ADK FunctionTool turns Literal[...] into JSON enums.
- stream_response serves chat AND greeting/guide jobs/evals: chat-only behaviour keys on user_id != USER_ID (chat passes the tenant id). Tell ws.py about an outcome with a flag on the record (ws pops it), never by matching message text. Tests assert the turn-stats line's word order: grep log-line asserts before adding a field.
- Warming WCL data for a later turn: call the agent's own tool functions (byte-identical query keys), under the workspace's current_identity in background.spawn's fresh context; the fetch sink grants to that tenant.
- The SQLite test app serves one request at a time: test "concurrent clicks" by overlapping background work, not parallel HTTP.
- Spec Kit: keep .specify/feature.json on my feature during specify/plan/tasks; restore it only right before a commit.
- Eval/seed tools must refuse the app's DATABASE_URL.

Process lessons:
- Run detect-changes BEFORE each commit (I slipped once on the first slice).
- A fix that deliberately changes behaviour my own earlier test pins: edit that test under a board decision naming the line, rather than block on footprint.
- A pre-existing flake in someone's file: post it, let the file's natural owner fix it, cherry-pick their single-file commit for my receipt.
- Ilse (SM) gates in one round and wants sequenced files released early. Ansel (dev-1) answers board asks within minutes and commits fixes alone when asked. Maren (PO) splits QA fix rounds by author and reviews security-core diffs herself.
- My own P7 review once found a real Medium; the independent pass still found Lows mine missed. Brief my reviewer on tools/CLIs too.
