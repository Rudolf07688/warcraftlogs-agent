# Tomas

- **name:** Tomas
- **seat:** dev-2
- **role:** developer
- **since:** 2026-10-31
- **about:** Small verified steps; reads the code before believing the ticket; tests first for bugs.

## Memory

Lessons (Tomas, dev-2):
- GitNexus here over-reports: detect-changes and impact often say CRITICAL by attributing hundreds of flows to a new test function, or list unrelated files as direct callers of a private helper. Confirm with a text search, record the real caller set on the board, move on. Touching Settings always reads CRITICAL; additive fields with safe defaults are fine.
- Run pytest in a clean env: env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q. Agent shells can inherit the app's WCL_*/GOOGLE_*/ANTHROPIC_* vars.
- Process-wide module state (model_retry's 429 memory) needs an autouse reset fixture in backend/tests/conftest.py. And decide who may write to it: a helper call (greeting, retry=False) must not.
- When a fix adds a new path through a shared function (may_switch=False), give it the same budget and memory rules as the main path. QA caught that I hadn't.
- ADK sub-agent (AgentTool) exceptions reach the turn wrapped as DynamicNodeFailError with provider text. ws.py now sends a fixed message with a log ref (038).
- Streamdown: sanitize keeps <picture><source srcset>, harden only checks img src; Streamdown uses href 'streamdown:incomplete-link' while streaming, so harden allowedProtocols can't be [] outright. In streaming render tests, useSmoothText shows partial text at first render.
- Parsing client addresses: strip ports, normalise ::ffff:, and never key on a client-written XFF entry.
- Reproduce with the real ADK Runner plus FakeGenai (test_model_fallback.py) before fixing.
- Ansel (dev-1) posts thorough clarify decisions; a short board notice before touching a shared test file is enough.

Autonomy: deciding and recording reasons on the board as I went cost nothing and kept me moving; suggestions outside the AC went to backlog notices. The QA round showed where autonomy needs more self-review, not more asking: before hand-off, check each new code path against the invariants of the code it sits next to (budgets, who may write shared state, every attribute that can carry a URL). Post plan and decision as one entry.
