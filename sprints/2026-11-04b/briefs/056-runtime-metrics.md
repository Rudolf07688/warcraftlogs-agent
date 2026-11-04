# Brief 056: runtime metrics (ADK metrics, app metrics, runtime dashboards D6–D8)

- **Feature / branch:** 056, `056-runtime-metrics`
- **Tier:** M (one Spec Kit pass: specify → plan → tasks → implement, no gates; answer your own clarify questions and record them on the board)
- **Seat:** `dev-3` (Nils). Parallel developers: Ansel (dev-1) on 055 build telemetry (owns Alloy, Mimir config and the recording-rule foundation), Tomas (dev-2) on 057 browser telemetry (owns `telemetry/__init__.py`, `ws.py`, `main.py`). Read the board's `contract:*` and `owner:*` keys first: they bind you.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (detached at the base). Base ref: sprint branch tip `sprint-2026-11-04b` = `3262948`. Create your branch there.
- **Security-core:** no. Label hygiene is the risk: bounded enums only, never ids, never `session.id` (contract:session-id).
- **Migration:** none.
- **Read first:** `specs/telemetry_spec.md` §6.3, §6.4, §8.2 (D6–D8), §8.3, §9, §14.2. The stories below win where they differ.

## Stories, in this order (AC verbatim from Shortcut)

### ADK core metrics by model and agent (sc-411, 2)
- ADK core metrics (`gen_ai.client.token.usage`, `gen_ai.invoke_agent.duration`, inference/tool calls per invocation) reach Mimir.
- Labels are enums only (model, agent, token type); no IDs.
- Semconv opt-in (`gen_ai_latest_experimental`) is set and versions are pinned.

PO notes: T1 already exports `gen_ai_client_token_usage` (the starter `observability/grafana/dashboards/runtime/app-api-llm.json` queries it), so find out what ADK emits today before adding anything. Every metric attribute must be in `METRIC_ATTRIBUTES` (`backend/app/telemetry/setup.py`, the View drops the rest). Set the semconv opt-in in code (setup), not compose (you don't own compose). "Versions pinned": `google-adk>=2.0.0` in `pyproject.toml` is not pinned; pin it to the locked version (ADK 2.x pins `opentelemetry-sdk<=1.42.1`, §14.2).

### App metrics: WCL cache hit/miss, knowledge-base retrieval, stream time to first token (sc-412, 3)
- `app.cache.requests` (cache, result: hit/miss/stale) for the WCL Redis cache.
- Knowledge-base retrieval latency, chunks returned, top score and empty-result counter.
- `app.llm.stream.ttft` by model and agent.
- Checked with an in-memory metric reader test; labels are bounded enums, no IDs.

PO notes: instruments in a new `backend/app/telemetry/metrics.py` (one definition per metric). The WCL cache is `wcl_agent/cache/cache.py`; KB retrieval is `backend/app/kb/search.py`. Put time-to-first-token in `backend/app/agent_runner.py`, not `ws.py` (Tomas owns it; contract:backend-files). Use the OTel metrics API only (no-op without a provider), so the suite runs unchanged with telemetry off.

### Runtime dashboards: API, agents and LLM, knowledge base (D6, D7, D8) (sc-413, 3), cut to D7 only if it slips
- D6 (API RED), D7 (agents and LLM) and D8 (knowledge base and embeddings) are provisioned as JSON and query recording-rule aliases.
- The panels populate from a live chat.

PO notes (decision:dashboards, comment on 413): D7 evolves `app-api-llm.json` (keep its uid); D6 (`api-red.json`) and D8 (`rag.json`, or similar) are new files in `observability/grafana/dashboards/runtime/`. Your aliases go in `observability/mimir/rules/<tenant>/runtime.yaml` (contract:recording-rules: `genai:tokens:rate5m`, `genai:invoke_agent_latency:p95`, `rag:retrieval_latency:p95`, `cache:hit_ratio`); lint it with a pinned `mimirtool` image. D6 queries Ansel's RED aliases (contract:red-aliases) and D7's cost panel queries his `genai:cost_usd:rate5m` (contract:cost-alias); build against the contract names even before his work merges. Exclude `/ws/chat` and `.*/generate` from latency panels.

## File footprint (stay inside it; board `owner:stream-b`)
- `backend/app/telemetry/setup.py`, `backend/app/telemetry/metrics.py` (new)
- `wcl_agent/cache/**`, `backend/app/kb/**`, `backend/app/agent_runner.py`
- `observability/mimir/rules/*/runtime.yaml` (only this file under `observability/mimir/`), `observability/grafana/dashboards/runtime/**`
- `pyproject.toml`, `uv.lock` (yours alone this sprint)
- `backend/tests/test_telemetry_bootstrap.py`, `backend/tests/test_telemetry_genai.py`, new `backend/tests/test_telemetry_metrics*.py`
- `specs/056-runtime-metrics/**`
- Nothing else (not `telemetry/__init__.py`, `ws.py`, `main.py`, compose, Alloy, `mimir.yaml`). Need something: ask on the board with key `owner:<path>`.

## Docker
No compose. A pinned `mimirtool` image for `rules lint/check` is fine. No live LLM calls: fakes and in-memory readers.

## Tests and proof
- `check.py run --as nils` on your committed tree (receipt matters). In-memory metric reader tests for every new instrument and for the attribute allowlist (a forbidden attribute is dropped); mutation-check the label hygiene with `mutate.py`.
- Dashboards: JSON parses, every panel expr uses an alias from the contracts or `runtime.yaml`.
- Live checks (team-lead runs them on the merged tip): post each as a board `question` with key `live-check:056` and exact steps (one chat turn → ADK and app metrics in Mimir; D6–D8 panels populate).

## Hand-off
Stories to Under Review, a board `handoff`, and your final result: branch, commits, files, the `check.py` RESULT and RECEIPT lines, risks, and an AC-by-AC mapping. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
