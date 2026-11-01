# Implementation Plan: Big-report turns that finish and cost less

**Branch**: `046-big-report-turns` | **Date**: 2026-11-01 | **Spec**: [spec.md](spec.md)

## Summary

Four small slices, in order: compact projection for big report tables (sc-334), a closing
no-answer message plus `outcome=empty` and a paragraph break in the turn runner (sc-302), data
delimiters on knowledge-search hits plus capped titles/guild names in chunk text (sc-328), and a
background kickoff pre-fetch with a playbook and `tool_calls=N` (sc-339). Decisions: board
`clarify:046-*`, summarised in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (backend + `wcl_agent`)
**Primary Dependencies**: FastAPI, Google ADK, SQLAlchemy async (all existing; nothing added)
**Storage**: existing raw store (`raw_fetches`) and Redis cache, read and written only through the existing client paths; no migration
**Testing**: pytest via `.claude/team/check.py`; fakes only (no WCL, no model)
**Target Platform**: Linux container
**Project Type**: web service (backend) + agent package
**Performance Goals**: table payload < 10k tokens (chars/4) for a 20-player kill; projection off the event loop
**Constraints**: footprint per brief (no `ws.py`, `cache.py`, `config.py`, `conftest.py`); `stored_data_tools.py` only the `get_stored_fight_table` hunk
**Scale/Scope**: 4 stories, ~9 files

## Constitution Check

- I Reuse: `background.spawn` for the pre-fetch; the agent's own tool functions for the fetches; `chunks.bounded` for caps; `with_envelope`/`was_truncated` for completeness. PASS
- II Small steps: one story per slice, each verified before the next. PASS
- III Simplicity: one projection function (generic over lists in the table), no new settings, no new dependency. PASS
- IV Typed boundaries: tool results stay dicts (existing ADK tool contract); pre-fetch takes `RequestIdentity`. PASS
- V Async: projection sizing via `asyncio.to_thread` like `_acap`; pre-fetch is a background task. PASS
- VI GitNexus: impact run on every edited symbol (see research R6). PASS
- VII shadcn: no UI. N/A
- VIII Backlog: sc-334/302/328/339 moved on Shortcut; follow-ups go to the board as `backlog:` notices. PASS

## Project Structure

```text
wcl_agent/tools/report_tools.py        # compact_table / acompact_table; get_report_table uses it
wcl_agent/agent.py                     # instruction: compact tables, <data> rule, RECENT_RAID_KICKOFF playbook
backend/app/agent_tools/stored_data_tools.py   # get_stored_fight_table hunk only
backend/app/agent_runner.py            # paragraph break, no-answer message, outcome=empty, tool_calls=N
backend/app/kb/search.py               # payload(): <data> wrapping + neutralising
backend/app/kb/wcl_chunker.py          # title / guild caps
backend/app/api/raids.py               # schedule the pre-fetch after the 404 rule
backend/app/services/kickoff_prefetch.py  # new: boss pick + bounded fetch
backend/tests/test_046_compact_tables.py, test_046_empty_turn.py, test_046_search_data.py,
backend/tests/test_046_kickoff_prefetch.py, backend/tests/fixtures/wcl_table_heroic_20.json
```

## Complexity Tracking

None.
