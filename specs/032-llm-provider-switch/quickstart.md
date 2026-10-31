# Quickstart: verify 032

All checks run with fakes. No key, no ADC, no live LLM.

## Automated

```bash
cd <worktree>
uv run --extra test pytest -q                                    # full backend suite, no new failures vs b963463
uv run --extra test pytest -q backend/tests/test_llm_provider.py \
  backend/tests/test_llm_provider_agent.py backend/tests/test_llm_provider_app.py \
  backend/tests/test_vertex.py
cd frontend && npm run build && npx vitest run src/App.modelFallback.test.tsx
```

| AC (sc-249) | Proven by |
|---|---|
| 1 switch values, invalid → vertex | `test_llm_provider.py` (provider parsing, warning once) |
| 2 one provider layer | `test_vertex.py` guard (no client constructor outside `provider.py`) |
| 3 agent on `AsyncAnthropic`, retry wrapper | `test_llm_provider_agent.py` (fake client via mock transport: chat turn with tools, greeting path, 429 retried; vertex picks `AsyncAnthropicVertex`; thinking adaptive; drop_block + beta header) |
| 4 secret, missing key | `test_llm_provider_app.py` (sentinel absent from logs, frames, `/api/*`, exception text; missing key: one error, degraded state, app up) |
| 5 id forms in one place | `test_llm_provider.py` (`to_provider_id` both ways, `served_ids`) |
| 6 stale chat model | `test_llm_provider_app.py` (WS turn on a Gemini id under anthropic runs on the default, no `invalid_model`); `App.modelFallback.test.tsx` (browser sends the served default) |
| 7 role defaults, explicit wins | `test_llm_provider.py` (all roles × providers; explicit Claude wins; Gemini under anthropic warned and replaced) |
| 8 docs, compose | Review `.env.example` and README provider section; compose unchanged (R9) |
| 9 fakes only, suite green | the suite itself |

## Owner live check (Under Review)

1. `.env`: `WCL_LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=…`; restart. Log shows
   `LLM provider: anthropic` and the Claude models probed. Chat a multi-tool question twice in the
   same chat (second turn exercises replayed thinking). The greeting appears.
2. Remove the key line, restart: one error line, the app loads, a chat turn shows a clear error.
3. Back to `vertex` (delete the line), restart: Gemini as before. Pick a Claude model on Vertex
   (if quota exists) and chat: Claude on Vertex works again.
