---
id: claude-prompt-cache-layout
anchors: [sym:wcl_agent/llm/model_retry.py::_turn_layout, sym:wcl_agent/llm/model_retry.py::_pin_time_block, sym:wcl_agent/agent.py::build_instruction]
by: dev-4 Vera
verified: a8f834d 2026-11-22
---
Claude chat requests carry at most four cache breakpoints (_turn_layout): the instruction head
(no tenant text), the end of the stubbed history older than keep_turns(), the last block, and the
tools or, once a previous turn start wrote one, that previous history end (Claude looks back only
~20 blocks). The time block leads the turn's user message. A system change (wrap-up, playbook), a
model switch or an effort change rewrites what follows it.
