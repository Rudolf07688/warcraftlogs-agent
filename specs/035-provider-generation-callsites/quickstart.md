# Quickstart: verify 035

All checks use fakes; no live LLM calls, no keys.

```bash
cd <worktree>
uv run --extra test pytest -q backend/tests/test_llm_generation.py \
  backend/tests/test_guide_pipeline_llm.py backend/tests/test_provider_e2e.py
uv run --extra test pytest -q backend/tests/test_suggestions.py \
  backend/tests/test_conversation_titles.py backend/tests/test_report_synthesis.py \
  backend/tests/test_guide_pipeline_run.py backend/tests/test_guide_reports.py \
  backend/tests/test_guide_pipeline_research.py
uv run --extra test pytest -q          # full suite
```

## Acceptance criteria → evidence

| AC | Evidence |
|---|---|
| 1 one entry point, no genai types/branches in the three modules | `test_provider_e2e.py` grep check; `test_llm_generation.py` retry-loop tests |
| 2 fast/report roles, fail-closed, timeouts | `test_llm_generation.py` (model per role under `anthropic`), `test_suggestions.py`, `test_conversation_titles.py`, `test_report_synthesis.py` (hanging fakes, errors) |
| 3 `generate_structured` both providers, one retry, `GuideModelError` | `test_guide_pipeline_llm.py` (misfit → retry → valid; two misfits → error; both providers) |
| 4 `generate_grounded` web search, `{title, uri}`, fetch rules | `test_guide_pipeline_llm.py` (search + fetch result blocks, pause_turn, `allowed_domains` with the flag off/on) |
| 5 author ≠ reviewer, web search disabled → clear error | `test_guide_pipeline_llm.py` (role defaults differ under `anthropic`; "not enabled" 400 → `GuideModelError` with the Console link); README section |
| 6 vertex unchanged, existing tests pass, fakes only | full suite green; Gemini request-shape assertions in the moved tests; `test_provider_e2e.py` |

## Live (owner, Under Review)

1. Anthropic Console → Settings → Capabilities: web search (and web fetch) enabled.
2. `WCL_LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=…`, restart: send a chat message (suggestions
   and a title appear), export a PDF report, run one class guide (cited sources present).
3. `WCL_LLM_PROVIDER=vertex` (or unset), restart: the same three on Vertex.
