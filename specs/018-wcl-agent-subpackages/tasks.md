# Tasks: Restructure `wcl_agent` into sub-packages

**Input**: `specs/018-wcl-agent-subpackages/` (plan.md, spec.md, research.md,
data-model.md, contracts/module-map.md, quickstart.md)

**Tests**: no new pytest tests (they would change the suite counts AC 4 compares). The
proof is the baseline count match plus the two one-off checks in `checks/`.

**Sub-agents**: none (approved by the scrum master). One rewrite script in the scratchpad
(not committed) applies the mapping; every edit is reviewed by hand.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [ ] T001 Write the rewrite script `rewrite.py` in the session scratchpad: mapping from `contracts/module-map.md`; rewrites flat dotted refs `wcl_agent.<m>` and path refs `wcl_agent/<m>.py`, splits `from wcl_agent import a, b` per package, and recomputes relative imports in `wcl_agent/**` from each file's new package (research R4)
- [ ] T002 [P] Write `specs/018-wcl-agent-subpackages/checks/import_smoke.py` (walk `wcl_agent`, import every module, then `backend.app.main`; print `ok`/error per module, exit 1 on any error)
- [ ] T003 [P] Write `specs/018-wcl-agent-subpackages/checks/ast_refs.py` (FR-012: resolve every `wcl_agent` import, relative import and `"wcl_agent.…"` string literal in `wcl_agent/**`, `backend/**`, `main.py`; flag package-object imports of `wcl_agent.cache` / `wcl_agent.tools`; print findings and the total)

## Phase 2: Foundational (the move)

- [ ] T004 `git mv` the 22 modules into `wcl_agent/{client,cache,tools,guides,llm,game}/` per `contracts/module-map.md`
- [ ] T005 Create the 6 `wcl_agent/<pkg>/__init__.py` files, each a one-line docstring only
- [ ] T006 Run the rewrite script on `wcl_agent/**` (relative imports, lazy imports, docstring paths) and review the diff by hand
- [ ] T007 Verify: `uv run python -c "import wcl_agent"` and every moved module imports (`checks/import_smoke.py` for the `wcl_agent` part)

**Checkpoint**: `wcl_agent` imports cleanly from its new layout; commit slice 1.

## Phase 3: User Story 1 + 2 — layout in place, nothing changes (P1)

**Goal**: every importer follows the move; behaviour identical.

**Independent Test**: suite counts = 926 passed / 3 skipped / 1 deselected; both checks report 0 findings.

- [ ] T008 [US2] Run the rewrite script on the 24 backend app/evals files (`backend/app/**`, `backend/evals/guides/**`; list in plan.md) and review the diff by hand
- [ ] T009 [US2] Verify `backend.app.main` and every edited app/evals module import (`checks/import_smoke.py`; `uv run python -c "import backend.evals.guides.__main__"` style for evals)
- [ ] T010 [US2] Run the rewrite script on the 42 test files in `backend/tests/` (imports, dotted `monkeypatch.setattr` strings, `caplog` logger names, `test_vertex.py` path exemption) and review the diff by hand
- [ ] T011 [US2] Run `uv run --extra test pytest -q`; counts MUST equal the baseline; on any difference stop and report to the scrum master
- [ ] T012 [US1] Run `checks/ast_refs.py` (0 findings) and the old-path `git grep` from `quickstart.md` (0 hits outside historical files); fix any miss, then re-run T011
- [ ] T013 [US1] Verify history: `git log --follow` on every moved file shows pre-move commits (after commit)

**Checkpoint**: commit slice 2 (backend + tests).

## Phase 4: User Story 3 — docs match the code (P2)

- [ ] T014 [P] [US3] Update the §4 file map and every old path in `documentation/ai_guide.md`
- [ ] T015 [P] [US3] Update old paths in `README.md`
- [ ] T016 [P] [US3] Update old paths in `documentation/live_model_probe.md`
- [ ] T017 [P] [US3] Update the line-2 comment in `frontend/src/lib/classColors.ts`
- [ ] T018 [US3] Re-run the old-path `git grep` over the living docs and `classColors.ts`: 0 hits

## Phase 5: Polish & cross-cutting (AC 6, hand-off)

- [ ] T019 `uv run wcl` and `uv run python main.py` with `--help` and no env vars: output and exit code identical to the captured base output
- [ ] T020 `docker build -f backend/Dockerfile -t wcl-backend:018 .` succeeds
- [ ] T021 Boot to ready: throwaway `docker run --rm -d` Postgres on 15418 and Redis on 16318, `uv run uvicorn backend.app.main:app --port 18018` with dummy WCL values and no Vertex credentials; `/api/health` ready; record the model source; stop the containers
- [ ] T022 Confirm `git diff --name-only <base>...HEAD` lists only granted files and `uv.lock` / `pyproject.toml` are untouched; restore `.specify/feature.json` and `CLAUDE.md` before each commit
- [ ] T023 Re-index the worktree with GitNexus and run `detect-changes --scope all`; run the full suite, `import_smoke.py` and `ast_refs.py` one last time
- [ ] T024 Write the backlog list (renames `cache/cache.py`, `tools/tools.py`; anything else spotted) and send the hand-off to the scrum master

## Dependencies

- T001–T003 before T004. T004 → T005 → T006 → T007 → T008 → T009 → T010 → T011 → T012 → T013.
- Phase 4 (T014–T017) can run any time after T004; T018 after them.
- Phase 5 after Phase 3 and 4.

## Parallel opportunities

- T002 and T003 (different files).
- T014–T017 (different files). All by me; no sub-agents.

## Implementation strategy

Slice 1 (`wcl_agent` imports) → slice 2 (backend + tests, count match; this is the MVP and
covers US1 + US2) → docs → AC 6 checks → hand-off.
