---
id: no-ruff-in-venv
anchors: [file:pyproject.toml]
by: dev-2 Tomas
source: meta/team/dev-2.md L12
verified: b9cf9a3 2026-11-05
---
ruff is neither a project dependency nor installed in `.venv`. Run it ad hoc with
`uvx ruff check --select F <paths>` to catch unused imports and undefined names.
