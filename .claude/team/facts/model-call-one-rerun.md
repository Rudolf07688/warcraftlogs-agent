---
id: model-call-one-rerun
anchors: [sym:wcl_agent/llm/model_retry.py::_watch, sym:wcl_agent/llm/model_retry.py::_within, sym:backend/app/agent_runner.py::_run_turn]
by: dev-4 Vera
verified: 4fc12a3 2026-11-22
---
A model call gets at most one re-run (Gemini empty STOP, Claude thinking-only max_tokens, Claude
streamed request past CLAUDE_CALL_TIMEOUT_S): the wrappers hold back the bad final via _watch
and call again. _count_rerun bumps model_requests, so a re-run is a round toward round_cap. The
runner resets a call's thought text when TurnStats.reruns changes: there is no final event
between a held-back call and its re-run. Bound tests patch CLAUDE_CALL_TIMEOUT_S or _clock.
