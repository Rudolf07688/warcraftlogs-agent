# Quickstart: verify feature 021

## Automated (CI, no Vertex)

```bash
cd /home/rudolf/dev/wcl-worktrees/dev-a
uv run --extra test pytest -q backend/tests/test_model_fallback.py backend/tests/test_model_fallback_ws.py
uv run --extra test pytest -q   # full suite: baseline 1008 passed / 3 skipped / 1 deselected, plus the new tests
cd frontend && npm run build
```

What the new tests prove, per acceptance criterion:

| AC | Test |
|---|---|
| 1 (switch to sibling; second → first) | `sibling_model` cases; Gemini fake client: model A answers 429, request completes on B, client saw `model=B` |
| 2 (both busy / no sibling → message; socket survives) | wrappers raise `ModelRateLimited` after one switch; ws test: `rate_limited` error, then the next turn is processed |
| 3 (notice; at most one switch) | one `model_fallback` record with both ids; both models 429 → exactly one switch; later requests routed to B |
| 4 (no duplicated history) | no switch once anything was yielded (mid-stream 429 re-raises); ws test stores the reply once |
| 5 (Gemini and Anthropic paths, fake 429s) | `RetryingGemini` with a fake genai client, `RetryingClaude` with a fake Anthropic client, both switch and no-sibling cases |

## Manual (owner, needs Vertex credentials)

1. Serve two flash versions (catalog mode, `flash:2`). Pick the newer one.
2. Force a rate limit on it. Easiest: temporarily set `WCL_MODEL_RETRY_ATTEMPTS=1` and
   send several broad questions quickly until the provider returns 429.
3. Expect: the status line shows "… is rate-limited — switching to …", the answer
   arrives, and a note "Answered by <older> (<newer> was rate-limited)" sits under it.
   The model selector still shows the newer model.
4. If a switch happens after tool calls in the same turn, check the backend log for a
   400 about thought signatures (research R5). There should be none.
5. With a Claude model, a 429 after retries shows the "try again in about a minute"
   message, and the next message works.
