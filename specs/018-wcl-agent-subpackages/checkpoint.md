# Checkpoint: feature 018 (resume notes)

- Worktree `/home/rudolf/dev/wcl-worktrees/dev-a`, branch `018-wcl-agent-subpackages`,
  base sprint tip `4f748c3` (code == `4923785`). Never push. Story sc-150 is In Progress.
- Spec signed off (changes 1–4 applied); plan approved; grant given 2026-10-25 for plan.md
  items 1–6. Released (do not edit without asking): `main.py`, `test_grounding.py`,
  `test_prompt_contract.py`, `test_startup.py`, `pyproject.toml`, `uv.lock`.
- Decisions: layout per `contracts/module-map.md`; keep basenames; empty `__init__.py`
  (docstring only); no shims; no sub-agents; logger renames accepted.
- Baseline: 926 passed, 3 skipped, 1 deselected (perf test, fails at base with `-m perf`).
- Base CLI output (`wcl --help`, `python main.py --help`, no env): "Missing required
  environment variables: WCL_CLIENT_ID, WCL_CLIENT_SECRET, GOOGLE_API_KEY" + hint, exit 1.
  Captured in the scratchpad as `wcl_help_base.txt` / `main_help_base.txt`.
- AC 6 boot: ports app 18018, Postgres 15418, Redis 16318; plain `docker run --rm -d`, no
  compose; dummy WCL values, no Vertex creds; do NOT read the owner's `.env`. If boot
  cannot reach ready without real credentials, stop and name the blocking variable.
- Before each commit: `git checkout -- CLAUDE.md .specify/feature.json` (scrum master's
  files; `.specify/feature.json` is modified locally to point at this spec dir).
- Implementation starts at T001 in `tasks.md`.
