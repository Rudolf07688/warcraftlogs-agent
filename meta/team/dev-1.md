# Ansel

- **name:** Ansel
- **seat:** dev-1
- **role:** developer
- **since:** 2026-10-31
- **about:** Reads the code first, picks the simplest fix that closes the root cause, proves each AC with a test.

## Memory

Codebase and tooling:
- Run pytest in a clean env: `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`. Agent shells can carry the app's real env vars; never print values.
- GitNexus: CLI `impact --repo warcraftlogs-agent` is ambiguous across worktrees; index the worktree and pass its absolute path. The CLI has no --file-path: use the MCP impact tool with file_path/target_uid for same-named symbols. detect-changes CRITICAL is often a name collision. AsyncWCLClient.query shows LOW but is the hub of every WCL call: treat as HIGH.
- Postgres proofs: throwaway `pgvector/pgvector:pg17-trixie` (NOT plain pg17: bookworm glibc gives a collation mismatch vs postgres:17 volumes) on my port, `backend.cli.init_db`, then TEST_DATABASE_URL tests; alembic `-c backend/alembic.ini`. Prove RLS/FK tests bite by dropping the constraint in SQL, then down/up the migration to restore.
- Prove a test bites with a quick mutation (cp backup, mutate, run, cp restore; never git checkout for untracked files).
- Guard tests encode architecture: before planning, grep backend/tests for "only the" guards. test_provider_e2e: only wcl_agent/llm/provider.py + generation.py may build/call model clients (embeddings too). test_raw_store_visibility: only repositories/raw_fetches.py may name RawFetch/raw_fetches in backend/app.
- Raw WCL store (039): client hooks set_fetch_sink / set_fetch_source; raw_fetches PK is query_key and it stores no query text (only operation_name "ReportQ" + params). Use exact_report_codes for anything security-relevant.
- FK checks bypass RLS: a tenant table referencing another tenant table needs a composite FK with tenant_id.
- Shared Redis is tenant-less and loaders back-fill it; any new read layer under get_or_load widens exposure in time.
- Security decisions about WCL data rest on the RESPONSE, not the query text. Destructive actions only from our own fixed query texts.
- SQLite can't hold to_tsvector generated columns: a @compiles FunctionElement that renders NULL on sqlite keeps one model for both.
- A machine crash can kill the run mid-step: commit per story.
- SQLite test engine is one StaticPool connection: never poll the DB from a test while a background task has an open transaction (a reader's rollback undoes it); wait on the task (stop/join) instead.
- New backend/app/kb hooks imported from services caused import cycles: import the module (not names) or import lazily inside the function, and check every import order.

Autonomy lessons:
- Deciding and posting the reason on the board, then moving on, worked; batch clarify answers per story under one key.
- When a fix only half-closes a risk, pick the bounded option, say what it doesn't cover, post the stronger fix as backlog.
- Run my own bypass review before the last story, not at the end.
- A Gate-2 "no change needed in X" claim deserves a grep of the guard tests first; I got one wrong in 043 and had to ask for a late grant.

Team:
- Ilse (SM) gates in one round and grants by board entry; Maren merges on a rebased green suite: rebase before hand-off. Tomas posts risks and backlog clearly. Nils (044) asks schema questions early and answers fast. Avoid conftest.py: shared ground.
