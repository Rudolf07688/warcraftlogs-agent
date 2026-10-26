# Quickstart: verify 030

1. `uv run --extra test pytest -q backend/tests/test_participants_tool.py backend/tests/test_profile_context.py` (faked WCL: raid, M+, null realm, filters, size budgets, preamble lines).
2. After 029 merges: `uv run --extra test pytest -q backend/tests/test_prompt_contract.py` (D5 clauses).
3. Owner, live at review: ask "who was in <report link>" and "add the dungeon characters to my friends, except the shaman" and check the roster and the ask-which-run behaviour.
