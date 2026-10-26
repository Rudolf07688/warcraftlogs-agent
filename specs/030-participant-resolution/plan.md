# Implementation Plan: Participant Resolution

**Branch**: `030-participant-resolution` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/030-participant-resolution/spec.md`. Shortcut sc-206. Design: `documentation/designs/self-aware-agent/participants-and-confirmation.html` (#resolution, #participants, #filters, #files, #tests). Decisions D5, D9, D10.

## Summary

A new slim WCL tool `get_report_participants(report_code, fight_id=0)` returns the real players of a report or fight (name, realm, region, class, spec, role) in a size-budgeted result. Run resolution (D5) is model behaviour fed by two preamble changes: a "Recent runs" line and report codes on the "Raids" line, both built from already stored rows. Filters ("except the shaman") are done by the model on the rows. No new GraphQL query, no cache family, no DB change.

## Technical Context

**Language/Version**: Python 3.12 (FastAPI backend + `wcl_agent` package); TypeScript only for an optional tool label
**Primary Dependencies**: existing `wcl_agent` client (`_report_fields`, `_fight_ids`, `with_envelope`), `roster_snapshot()`; no new dependency
**Storage**: none new. Reads existing `tracked_raids`, `recent_raids`, `recent_mplus_runs` through existing repository functions
**Testing**: pytest with faked WCL responses (`backend/tests/wcl_fakes.py` pattern)
**Target Platform**: Linux server (existing app)
**Project Type**: web service (backend + agent package)
**Performance Goals**: one WCL request per lookup; preamble gains at most about 600 chars and no extra WCL calls (one or two small DB reads)
**Constraints**: row at most 120 chars, M+ result at most 1,500, 40-player raid at most 6,000, never `_truncated`; `wcl_agent` stays DB-free
**Scale/Scope**: 5 to 40 players per lookup, at most 5 candidates per kind

## Constitution Check

| Principle | Status |
|---|---|
| I Reuse | Passes: `_report_fields`, `_fight_ids`, `with_envelope`, `roster_snapshot()` (class and role validity), existing `repo.list_recent_*`; no new query or cache family. The group walk mirrors `datasheet._player_details`; if a third copy appears it is factored into one helper (see research R2). |
| II Small verified steps | Passes: tool and parser first (tests), then preamble, then late registration/guidance. |
| III Simplicity | Passes: one function, no filter arguments, no list-runs tool. |
| IV Typed boundaries | Passes: `Participant` typed dict/model, one pure parser. |
| V Async FastAPI | Passes: tool is async through the single client; preamble reads are awaited. |
| VII shadcn | N/A (at most a label string). |

Re-check after design: unchanged, no violations.

## Project Structure

### Documentation (this feature)

```text
specs/030-participant-resolution/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/get_report_participants.md
├── tasks.md (next step)  checkpoint.md
```

### Source Code

```text
wcl_agent/tools/participants.py              NEW: get_report_participants + participants_from_player_details
backend/app/services/profile_context.py      recent-runs line, report codes on Raids line
backend/app/services/raids.py                add tool name to REPORT_SCOPED_TOOLS
frontend/src/toolLabels.ts                   label for the tool (optional, one line)
frontend/src/lib/spells.ts                   optional label, only if the label list lives there
backend/tests/test_participants_tool.py      NEW
backend/tests/test_profile_context.py        recent-runs and report-code cases
-- only after 029 merges --
wcl_agent/agent.py                           TOOL_GROUPS/TOOLS registration + <RUN_RESOLUTION> guidance
backend/app/api/ws.py                        _build_turn_preamble: two reads + one kwarg
backend/tests/test_prompt_contract.py        D5 clause test
```

## Design

1. **Tool.** `_report_fields(code, "region { slug } playerDetails(fightIDs: $fightIDs)", ", $fightIDs: [Int]", {"fightIDs": _fight_ids(fight_id)})`. Pure `participants_from_player_details(details, region)` walks `data.playerDetails.{tanks,healers,dps}`. Class = `type`, realm = `server` (else `null`; every key read tolerates absence), spec = highest-count entry of `specs`, role = the role of that spec from `roster_snapshot()` when known, else the group the player was first seen in. A player present in several groups is merged by (name, realm). Entries whose class is not a playable roster class (pets, NPCs) are dropped. Sorted tank, healer, dps, then name. Errors use the standard `{"status": "error", ...}` shape; a result with zero players is an error ("no players found"), not an empty success.
2. **Tracking.** Add `get_report_participants` to `REPORT_SCOPED_TOOLS`.
3. **Preamble.** `build_preamble` gets two optional kwargs (`recent_raid_runs`, `recent_mplus_runs`) defaulting to empty, so existing output is byte-identical when empty. `_recent_block` appends `(report <code>)` to each Raids label and adds the two "Recent ..." lines, newest first, at most 5 each, whole block trimmed to about 600 chars for the new lines. `ws._build_turn_preamble` reads `repo.list_recent_raids` / `list_recent_mplus_runs` (limit 5) and passes them in.
4. **Guidance.** A short `<RUN_RESOLUTION>` paragraph in `agent.py` states the D5 order, kind mapping ("the dungeon" is M+, "the raid" is a raid), the one-candidate confirm, the 5-candidate cap, and filtering on the rows.

### How "asks when ambiguous" is tested without a live model (SC-003)

Deterministic only: (a) preamble tests show several candidates with report codes, kind labels and the 5 cap; (b) a prompt-contract test asserts the D5 clauses ("last"/"latest", ask, at most 5, never guess) are present in the instruction; (c) tool tests prove nothing is fetched by the tool itself without a report code. A scripted-model test is optional and a live-model assertion is not promised.

### Fixtures are Inferred

No live WCL call (agents never read the owner's credentials). Fakes follow the `playerDetails` shape already used in `datasheet._player_details` and `test_guide_pipeline_datasheet.py` (`data.playerDetails.{tanks,healers,dps}`, entries with `name`, `type`, `server`, `specs`). Key names `server` and `specs` and the class value format are Inferred; the owner verifies against live data at Under Review.

## Impact (GitNexus, upstream, index 1 commit behind HEAD)

| Symbol | Risk | Callers | Mitigation |
|---|---|---|---|
| `build_preamble` | HIGH (6 impacted, 3 processes) | `ws._build_turn_preamble`, `evals/guides/coaching.build_case_preamble` (+ `_handle_turn`, `run_case`); 20 calls in `test_profile_context.py` | Only optional kwargs defaulting to empty are added; with nothing stored the output is byte-identical, asserted by the existing 20 tests plus a new byte-identity test. Raised with the scrum master before editing. |
| `_recent_block` | LOW (1 direct: `build_preamble`) | via `build_preamble` | Same byte-identity guarantee. |
| `_build_turn_preamble` | LOW (1 direct: `_handle_turn`; process `chat`) | `ws._handle_turn` | Two extra reads and kwargs only; edit waits for 029. |
| `REPORT_SCOPED_TOOLS` | UNKNOWN | no edges; text search finds one reader, `raids.py:112` (`name not in REPORT_SCOPED_TOOLS`) | Adding a name only widens a membership test in that one place. |
| `_report_fields` | read-only reuse, not edited | | |

## File list for the ownership grant

Now: `wcl_agent/tools/participants.py` (new), `backend/app/services/profile_context.py`, `backend/app/services/raids.py`, `frontend/src/toolLabels.ts`, `frontend/src/lib/spells.ts` (only if labels live there), `backend/tests/test_participants_tool.py` (new), `backend/tests/test_profile_context.py`, `specs/030-participant-resolution/**`.

After 029 merges: `wcl_agent/agent.py`, `backend/app/api/ws.py`, `backend/tests/test_prompt_contract.py`.

No dependency change and no migration.
