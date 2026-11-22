---
id: model-call-one-rerun
anchors: [sym:wcl_agent/llm/model_retry.py::_watch, sym:wcl_agent/llm/model_retry.py::_within, sym:backend/app/agent_runner.py::_run_turn]
by: dev-4 Vera
verified: 4fc12a3 2026-11-22
---
A model call gets at most one re-run (Gemini empty STOP, Claude thinking-only max_tokens or cut
at CLAUDE_CALL_TIMEOUT_S before answer text): _watch holds back the bad final. A re-run counts as
a round. The runner resets thought text when TurnStats.reruns changes. No Gemini re-run once
TurnStats.answer_shown; a Claude cut after answer text ends with CUT_LINE (time_cuts). _within
counts only provider wait time. Bound tests patch CLAUDE_CALL_TIMEOUT_S or _clock.
