---
id: tool-docstring-is-prompt
anchors: [file:wcl_agent/tools/, file:backend/app/agent_tools/, sym:wcl_agent/agent.py::drop_schema_titles]
by: dev-4 Vera, dev-2 Tomas
verified: 9ff8602 2026-11-07
---
A tool's whole docstring is its model-facing description, sent every request. Keep usage rules
in one place (docstring or instruction); leave result shapes out. ADK adds no
per-parameter descriptions; agent.drop_schema_titles strips pydantic titles. test_064_prompt_budget caps
instruction plus schemas at 12,800 chars/4 per provider. Prompt text is pinned verbatim, some
pins across line breaks, in backend/tests/test_{prompt_contract, 046_compact_tables,
046_search_data, 050_report_fights (also a docstring), 050_kickoff_overview, kb_search_prompt,
kb_eval, profile_tools}.py; test_capabilities requires every tool to have a docstring.
