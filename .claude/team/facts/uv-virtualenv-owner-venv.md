---
id: uv-virtualenv-owner-venv
anchors: [file:pyproject.toml, file:uv.lock]
by: dev-3 Nils
source: meta/team/dev-3.md L33; meta/sprints/2026-11-05/board.jsonl #48
verified: 32010a6 2026-11-05
---
Agent shells carry `VIRTUAL_ENV=/home/rudolf/dev/warcraftlogs-agent/.venv`, the owner's
checkout. So `uv pip ...` run in a worktree changes the owner's venv, and `uv run`/`uv sync`
warn. For lockfile and dependency work in a worktree, use `env -u VIRTUAL_ENV uv lock` and
`env -u VIRTUAL_ENV uv sync`.
