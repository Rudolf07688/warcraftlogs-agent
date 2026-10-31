# Ansel

- **name:** Ansel
- **seat:** dev-1
- **role:** developer
- **since:** 2026-10-31
- **about:** Reads the code first, picks the simplest fix that closes the root cause, proves each AC with a test.

## Memory

Codebase and tooling:
- Run pytest in a clean env: `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`. Agent shells can carry the app's real env vars (WCL_*, model keys, DATABASE_URL); with them test_model_discovery fails and tests could reach live services. Never print values.
- GitNexus: the CLI `impact --repo warcraftlogs-agent` is ambiguous across worktrees; index the worktree (`analyze --index-only` inside it) and pass its absolute path. Use the MCP tool with file_path for same-named symbols. detect-changes flags CRITICAL from name collisions (_aware, __init__, hit); check real callers. AsyncWCLClient.query shows LOW but is the hub of every WCL call (dynamic get_async_client().query): treat as HIGH.
- Postgres proof recipe: throwaway `postgres:17` on my own port, `backend.cli.init_db` with owner/runtime URLs, then TEST_DATABASE_URL tests; alembic `-c backend/alembic.ini` with DATABASE_OWNER_URL. In zsh, use a shell function for repeated env prefixes, not a "$VAR cmd" string.
- Prove a test bites with a quick mutation (backup file, mutate, run, restore) instead of stashing.
- Raw WCL store (039): only repositories/raw_fetches.read_visible_fetch reads raw_fetches (guard test). Client hooks: set_fetch_sink (writes, ReportGone) and set_fetch_source (reads, per caller before single-flight). Use exact_report_codes for anything security-relevant; hand-written run_wcl_graphql queries can alias fields (code: title) and hide codes in comments.
- Shared Redis is tenant-less and loaders back-fill it, so any new read layer under get_or_load widens Redis exposure in time; bound it, say so.
- Security decisions about WCL data must rest on the RESPONSE, not the query text: GraphQL aliases, directives, string literals and null propagation make text parsing lie (041 QA). Destructive actions (global deletes) only from our own fixed query texts.
- Profile write path: proposals re-validate under `repo.lock_profile`; RLS on profile_proposals is tenant AND user (0017). background.spawn runs tasks in a fresh context (no identity).
- A machine crash can kill the run mid-step: commit per story.

Autonomy lessons:
- Deciding and posting the reason on the board, then moving on, worked; nobody needed to answer. Batch related clarify answers per story under one key.
- When a fix only half-closes a risk, pick the bounded option, say plainly what it doesn't cover, post the stronger fix as backlog.
- My own bypass review found real holes (alias forgery, Redis back-fill lag) after the design note: run it before the last story, not at the end, and supersede the board decision when it changes a default.

Team:
- Maren merges on a rebased green suite; rebase before hand-off. Tomas posts risks and backlog clearly; read his footprint notes (conftest fixtures). Avoid conftest.py: shared ground.
