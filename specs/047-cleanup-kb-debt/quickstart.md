# Quickstart: Clean-up and KB debt

## Where `.env` is loaded (sc-336)

| Run | Loads `.env` through | Changed? |
| --- | --- | --- |
| docker compose | `env_file: .env` in `docker-compose.yml`, plus `backend/app/config.py` | no |
| `uv run uvicorn backend.app.main:app` | `load_dotenv()` and `Settings.env_file` in `backend/app/config.py` | no (switch defaults on) |
| CLI `wcl_agent/cli.py` | `load_dotenv()` in `_main()` | no |
| test suite | nothing: `backend/tests/conftest.py` sets `WCL_LOAD_DOTENV=0` first | yes |

`WCL_LOAD_DOTENV=0` also runs the app without its `.env` (env vars only).

## Verify

```bash
python3 .claude/team/check.py run --as ansel                 # full suite, SQLite
python3 .claude/team/pg.py up ansel
python3 .claude/team/check.py run --pg ansel --as ansel      # full suite incl. Postgres tests
python3 .claude/team/pg.py down ansel
```

Fake `.env` proof (never the owner's): write `.env` with sentinel values in the worktree, run
`check.py run --allow-env`, compare counts with the clean run, delete the file.

## Live check (team-lead)

1. Ask the agent "which stored reports is <character> in" twice; answers as before, fast.
2. `/api/.../wcl-cache` stats: local-answer turns don't rise when a turn waits on another
   turn's WCL load.
