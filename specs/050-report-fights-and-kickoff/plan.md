# Implementation Plan: Report fights and kickoff

**Branch**: `050-report-fights-and-kickoff` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

## Summary

Four small, independent changes to the agent's report tools and knowledge search:
`get_report_fights` gains `last_kill` and `bosses` computed from the full fight list (sc-365);
one difficulty map in `wcl_agent/game/constants.py` (sc-330); a slim `overview` table view and a
kickoff-only playbook (sc-358); one neutraliser for data blocks, hit labels and sections inside
them, and capped uploader strings in report tools (sc-351).

## Technical Context

**Language/Version**: Python 3.14 (backend, wcl_agent)
**Primary Dependencies**: Google ADK (InstructionProvider, FunctionTool), FastAPI, SQLAlchemy
**Storage**: none changed (no migration); cached `ReportSummary` shape unchanged
**Testing**: pytest via `check.py`; fixtures only, no WCL or model calls
**Target Platform**: Linux server (docker compose in production; not run here)
**Project Type**: web service + agent library
**Performance Goals**: kickoff answer request at least 15k tokens smaller (synthetic fixture)
**Constraints**: no change to WCL queries (the kickoff pre-fetch and raw store key on query text)
**Scale/Scope**: 4 stories, 7 pts

## Constitution Check

- I Reuse-first: `boss_summary` reuses `ReportSummary`; overview reuses `_compact_level`; one
  neutraliser, one string-cap helper, one difficulty map. PASS
- II Small steps: one commit per story, each verified by tests. PASS
- III Simplicity: no new query fields, no new tool, a flag on an existing tool. PASS
- IV Typed boundaries: tool results stay plain dicts at the ADK boundary (existing pattern);
  inputs typed. PASS
- V Async: no new I/O; projections stay off the loop through the existing `to_thread`. PASS
- VI GitNexus: impact run on every edited symbol (board notices). PASS
- VII shadcn: no UI. N/A
- VIII Backlog: stories moved on Shortcut by the developer. PASS

## Project Structure

### Documentation (this feature)

```text
specs/050-report-fights-and-kickoff/
├── plan.md, research.md, data-model.md, quickstart.md, checkpoint.md, tasks.md
└── contracts/report-tools.md
```

### Source Code (repository root)

```text
wcl_agent/game/constants.py        # DIFFICULTY_NAMES (sc-330)
wcl_agent/tools/tools.py           # imports it (sc-330)
wcl_agent/tools/report_tools.py    # boss_summary/last_kill, overview, string caps (365/358/351)
wcl_agent/agent.py                 # last_kill clause, kickoff-only playbook (365/358)
backend/app/api/raids.py           # kickoff_prompt_for uses RAID_KICKOFF_OPENING (358)
backend/app/services/name_resolver.py, profile_context.py   # import the map (330)
backend/app/kb/search.py           # neutraliser, label/section data blocks (351)
specs/044-kb-search/contracts/search-knowledge.md          # result shape (351)
backend/tests/test_050_*.py        # new tests; test_046_search_data.py, test_046_kickoff_prefetch.py edits
```

**Structure Decision**: existing modules only; no new package.

## Complexity Tracking

None.
