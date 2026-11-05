---
id: tool-docstring-is-prompt
anchors: [file:wcl_agent/tools/, file:backend/app/agent_tools/, sym:wcl_agent/agent.py::drop_schema_titles]
by: dev-4 Vera
verified: 0678ea7 2026-11-05
---
A tool's whole docstring (Args and Returns too) is its model-facing description, sent on every
model request; ADK adds no per-parameter descriptions. Keep usage rules in one place (docstring
or instruction policy, not both) and leave result shapes out: the model reads them in the
result. agent.drop_schema_titles strips pydantic 'title' keys from the sent schemas.
test_064_prompt_budget pins instruction plus schemas (chars/4) per provider; raise its budget
only with a measurement.
