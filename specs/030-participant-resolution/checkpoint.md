# Checkpoint: 030 Participant Resolution (2026-10-26)

**State**: specify, clarify, plan, tasks done and signed off through the plan; implementation held for "GO implement 030". Branch `030-participant-resolution`, base sprint tip (1da8bca; sprint artefacts moved to 139a0e7, no rebase needed).

**Decisions**: tool `get_report_participants(report_code, fight_id=0)` in `wcl_agent/tools/participants.py`; one `_report_fields` call with `region { slug } playerDetails`; missing realm becomes null (D12 correction), tolerate missing keys; swap handling: most-played spec and its roster role, else first group; zero players or inaccessible gives standard error; filters are model-side; no live WCL call, fakes are Inferred from `datasheet._player_details` and `test_guide_pipeline_datasheet.py`, owner verifies live at review. SC-003 tested deterministically (preamble candidates plus prompt-contract clause).

**Owned files now**: `wcl_agent/tools/participants.py`, `backend/app/services/profile_context.py`, `backend/app/services/raids.py`, `frontend/src/toolLabels.ts`, `frontend/src/lib/spells.ts`, `backend/tests/test_participants_tool.py`, `backend/tests/test_profile_context.py`, `specs/030-participant-resolution/**`. After 029 merges: `wcl_agent/agent.py`, `backend/app/api/ws.py`, `backend/tests/test_prompt_contract.py`.

**Impact**: build_preamble HIGH (kwargs optional, byte-identical output), others LOW, REPORT_SCOPED_TOOLS UNKNOWN but one text-search reader (see plan).

**Open**: the exact `server`/`specs`/`type` formats of live `playerDetails` and the class value format versus roster `class_name` are Inferred.

**Resume at**: tasks.md T001. Ports 18030/15430/16330. Restore `CLAUDE.md` and `.specify/feature.json` before each commit.

**Baseline (before code)**: full backend suite 1066 passed, 3 skipped, 1 deselected.
**Phases 1-4 done**: suite 1081 passed, 3 skipped, 1 deselected; `npm run build` ok. detect-changes: medium, only `build_preamble` flows (eval run_case), kwargs optional. Next: phase 5 after "029 MERGED, rebase".
