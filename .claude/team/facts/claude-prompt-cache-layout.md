---
id: claude-prompt-cache-layout
anchors: [sym:wcl_agent/llm/model_retry.py::_turn_layout, sym:wcl_agent/llm/model_retry.py::_pin_time_block, sym:wcl_agent/agent.py::build_instruction]
by: dev-4 Vera
verified: 9ea3f72 2026-11-20
---
Claude chat requests carry four cache breakpoints (079, 087 _turn_layout): tools, the
instruction head (shared by all tenants: never put tenant text in the system), the end of the
history older than keep_turns() (stubbed, so stable), and the last block. The turn's pinned time
block leads the turn's user message, not the system. A change to the system (wrap-up, kickoff
playbook), a stub boundary move, a model switch or an effort change rewrites what follows it.
Check usage cache_creation_input_tokens per call.
