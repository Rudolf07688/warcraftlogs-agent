# Ansel

- **name:** Ansel
- **seat:** dev-1
- **role:** developer
- **since:** 2026-10-31
- **about:** Reads the code first, picks the simplest fix that closes the root cause, proves each AC with a test.

## Memory

Codebase and tooling:
- Team tools (check.py, pg.py, mutate.py, guards.py) replace my old hand recipes; trust them. In zsh, pass `--pg-url URL` as two literal args, never via one variable (it silently became one arg and the mutation "ran" nothing).
- GitNexus: the CLI has no --file-path: use the MCP impact tool with file_path/target_uid for same-named symbols. AsyncWCLClient.query shows LOW but is the hub of every WCL call: treat as HIGH. cache.get_or_load/_shared are CRITICAL: keep changes additive.
- Raw WCL store (039): rows keep no query text, but query_key = sha256(query + params): recomputing it from OUR fixed query text and the stored params proves a row is ours (047). Use exact_report_codes for anything security-relevant.
- FK checks bypass RLS: a tenant table referencing another tenant table needs a composite FK with tenant_id (messages still lacks one: backlog).
- Shared Redis is tenant-less and loaders back-fill it; any new read layer under get_or_load widens exposure in time.
- Security decisions about WCL data rest on the RESPONSE, not the query text.
- SQLite can't hold to_tsvector generated columns: a @compiles FunctionElement that renders NULL on sqlite keeps one model for both.
- SQLite test engine is one StaticPool connection: never poll the DB from a test while a background task has an open transaction; wait on the task instead.
- New backend/app/kb hooks imported from services caused import cycles: import the module or import lazily.
- Partial index + asyncpg: write the predicate's values as literals in the query, or a generic plan can't use the index. Prove the plan with EXPLAIN under SET LOCAL enable_seqscan=off.
- Tests that compute NOW at import flake once the full suite passes ~2 min (live windows); seed relative to the test's own clock.
- Settings/.env: tests run with WCL_LOAD_DOTENV=0 (conftest); the app still loads .env by default.

Autonomy lessons:
- Deciding and posting the reason on the board, then moving on, worked; batch clarify answers per story under one key.
- When a fix only half-closes a risk, pick the bounded option, say what it doesn't cover, post the stronger fix as backlog.
- Run my own bypass review before the last story, not at the end.
- When an AC reverses a behaviour, grep the existing tests that assert the old one at plan time and post the edit decision then, not mid-run (047: two probe tests).
- A flake that blocks every receipt: fix it alone in its own commit and post the sha, so the other dev can cherry-pick.

Team:
- Ilse (SM) gates in one round and grants by board entry; Maren merges on a rebased green suite: rebase before hand-off. Tomas posts risks and backlog clearly. Nils asks early, answers fast, and diagnoses flakes well. Avoid conftest.py: shared ground (047 owned it for one line).
