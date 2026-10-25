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

## Status 2026-10-25 (implementation done)

- T001–T023 done; T024 = hand-off message to the scrum master.
- Commits on the branch: f176dc2, 7563479, 4393362, da37290 (spec/plan/tasks),
  cb9367a (moves + imports), bc112ef (docs), plus this checkpoint/tasks commit.
- Results: suite 926 passed / 3 skipped / 1 deselected (= baseline); `import_smoke.py`
  33 modules, 0 failed; `ast_refs.py` 213 files, 229 imports, 10 strings, 0 findings;
  old-path grep 0 hits; 22/22 moved files keep history (`--follow` = base + 1);
  `wcl` / `python main.py` output and exit code 1 identical to base; image builds and all
  33 modules import inside it; boot on 18018 reached `ready` (roster fallback 40 specs,
  models degraded: 2 static fallback models, no Vertex creds).
- Slice 1 was not committed on its own (the backend was broken in between), so the code
  lands as one commit, cb9367a.
