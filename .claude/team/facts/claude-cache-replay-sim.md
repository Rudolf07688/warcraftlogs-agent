---
id: claude-cache-replay-sim
anchors: [file:backend/tests/test_087_history_cache.py, comp:telemetry]
by: dev-4 Vera
verified: 7a90bcc 2026-11-22
---
Cache-layout changes can be measured offline: test_087_history_cache.simulate replays captured
Anthropic request bodies (scripted transport, real agent path) through a model of Claude's
prefix cache (an entry per breakpoint, 20-block look-back) and returns chars read, written and
sent fresh per request. Cost them read 0.1, write 1.25, fresh 1. Use it before a live check; it
matched the prototype numbers in measure:087.
