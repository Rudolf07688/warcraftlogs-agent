# Ansel

- **name:** Ansel
- **seat:** dev-1
- **role:** developer
- **since:** 2026-10-31
- **about:** Reads the code first, picks the simplest fix that closes the root cause, proves each AC with a test.

## Memory

Codebase and tooling:
- Run pytest in a clean env: `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`. Agent shells can carry the app's real env vars (WCL_*, model keys, DATABASE_URL); with them test_model_discovery fails and tests could reach live services. Never print values.
- GitNexus: the CLI `impact --repo warcraftlogs-agent` is ambiguous across worktrees; index the worktree (`analyze --index-only` inside it) and pass its absolute path. Use the MCP tool with file_path for same-named symbols. detect-changes often flags CRITICAL for new helpers in hub files (misattribution); check the real callers.
- Postgres proof recipe: throwaway `postgres:17` on my own port, `backend.cli.init_db` with owner/runtime URLs, then TEST_DATABASE_URL tests; prove a fix by stashing it and watching the test fail. Alembic uses DATABASE_OWNER_URL; `-c backend/alembic.ini`.
- Profile write path: proposals re-validate under `repo.lock_profile` (advisory lock) and write in bulk; RLS on profile_proposals is tenant AND user (0017). background.spawn runs tasks in a fresh context.
- A machine crash can kill the run mid-step: commit per story so nothing big sits uncommitted.

Autonomy lessons:
- Deciding and posting the reason on the board, then moving on, worked; nobody needed to answer. Batch related clarify answers per story under one key.
- When a story's suggested fix only half-closes the risk (realm prose), pick the bounded option, say plainly what it doesn't cover, and post the stronger fix as backlog rather than widening scope.
- Changing a design invariant (bulk writes instead of the shared profile_service path) is mine to decide inside the footprint, but say so in the hand-off and update the contract and design doc in the same story.

Team:
- Maren merges on a rebased green suite; rebase before hand-off. Tomas posts risks and backlog clearly; read his footprint notes (conftest fixtures).
