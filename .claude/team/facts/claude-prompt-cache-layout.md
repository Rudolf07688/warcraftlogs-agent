---
id: claude-prompt-cache-layout
anchors: [sym:wcl_agent/llm/model_retry.py::_pin_time_block, sym:wcl_agent/agent.py::build_instruction]
by: dev-4 Vera
verified: 9ea3f72 2026-11-20
---
Claude chat requests cache three prefixes (079): tools, the instruction up to <CURRENT_TIME>,
and the conversation's last block (RetryingClaude sets ADK's cache_config). The time block is
split off and pinned per turn (TurnStats.pinned_time). Text that varies per request must go
after the time block or into the turn's user message: anything changing earlier in the
instruction, a model switch or an effort change voids the history cache for that call. Check
usage cache_creation_input_tokens per call.
