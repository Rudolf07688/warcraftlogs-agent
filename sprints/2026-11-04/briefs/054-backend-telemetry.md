# Brief 054: backend telemetry (bootstrap, one-turn traces, GenAI spans, logs, content policy)

- **Feature / branch:** 054, `054-backend-telemetry`
- **Tier:** M (one Spec Kit pass: specify → plan → tasks → implement, no gates; answer your own clarify questions and record them on the board)
- **Seat:** `dev-3` (Nils). Parallel developer: Ansel (dev-1) on 053 telemetry stack (Alloy, compose, wrapper), disjoint files.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (detached at the base). Base ref: sprint branch tip `sprint-2026-11-04` = `38606fd`. Create your branch there.
- **Security-core: yes.** Chat text, tool I/O and WCL data leave the process. At hand-off I run an independent qa-security review on `sprint-2026-11-04...054-backend-telemetry`; its Highs and Mediums are your one rework round.
- **Migration:** none.
- **Read first:** `specs/telemetry_spec.md` §6.1–6.3, §6.6 (API → ADK only), §10, §14 (decisions 1, 3, 7, 12 and §14.2 constraints are binding). The stories below win where they differ.

## Stories (acceptance criteria verbatim from Shortcut)

### Backend telemetry bootstrap, off unless configured (sc-402, 3)
- `backend/app/telemetry/` sets the global tracer, meter and logger providers before ADK is imported, with resource `service.name=api`, `service.version`/`vcs.ref.head.revision` = git sha, `app.layer=runtime`, `deployment.environment.name`.
- Exports over OTLP http/protobuf (no grpcio) to Alloy; metrics cumulative with exponential histograms.
- With no OTLP endpoint set, no providers or instrumentors are installed and the test suite is unchanged.
- OpenTelemetry packages stay within ADK's pin (`opentelemetry-sdk<=1.42.1`, contrib 0.63b1).

### One chat turn is one trace: FastAPI, SQLAlchemy, Redis and httpx instrumentation (sc-403, 3)
- FastAPI (routes as templates; `/health` and readiness excluded), SQLAlchemy on the single engine (`backend/app/db/session.py`, also used by ADK's session store), Redis and httpx are instrumented.
- One chat turn yields one trace: HTTP → `invoke_agent` → `generate_content` / `execute_tool` → WCL httpx → SQL → Redis, proven with an in-memory exporter test.
- Queue-fed background writers (FetchWriter, KbIndexer) may start their own traces; this is documented.
- No google-genai instrumentation in this sprint (it would duplicate ADK's inference span).

### GenAI spans for one-shot model calls (titles, suggestions, reports, guides, embeddings) (sc-404, 2)
- One manual GenAI span in `wcl_agent/llm/generation.py` with `gen_ai.*` attributes (operation, request model, usage tokens, finish reason).
- A chat-title call shows model and tokens for Claude (vertex and anthropic providers) and for Gemini.
- Second to drop in sprint 1 if it slips.

### Backend logs to Loki with trace ids, through the redaction filter (sc-405, 2)
- An OTLP log handler exports with `trace_id`/`span_id`; stdout logging stays as the fallback.
- The handler gets `RedactionFilter` explicitly: `_install_log_redaction` only covers handlers that exist when it runs (`backend/app/main.py:63-68`).
- A log line opens its trace in Grafana; a test shows a token passed in `extra` is exported redacted.

### Content-capture policy per environment (on in dev, off elsewhere) (sc-406, 2)
- In dev, prompts, responses and tool I/O are present on ADK spans/events and land in the 7-day content stream.
- In ci/prod the three ADK lockdown settings apply (`ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`, `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT`, `ADK_TELEMETRY_IGNORE_RUN_CONFIG=1`); tests prove no content is exported. ADK's default is content ON, so the default must be explicit.
- An app-side redaction span processor masks secrets even with content on (test).

Order: 402 first, then 406 and 405 (security), then 403, then 404.

## File footprint (stay inside it)
- `backend/app/telemetry/**` (new)
- `backend/app/main.py`: only the bootstrap call (before the ADK import at line 13) and the OTLP log handler wiring next to `_install_log_redaction`. No other hunks.
- `backend/app/config.py`: only new settings fields for telemetry, if you need them.
- `wcl_agent/llm/generation.py`: the one GenAI span (sc-404).
- `pyproject.toml`, `uv.lock` (granted: yours alone this sprint; OTel deps within the ADK pin)
- `.env.example` (document the telemetry env vars)
- `backend/tests/test_telemetry*.py` (new); shared fixtures only in new files.
- `specs/054-backend-telemetry/**`
- Not yours: `docker-compose.yml`, `observability/**`, `bin/**` (stream A). Need something else: ask on the board with key `owner:<path>`.

## Contracts with stream A (also on the board, keys `contract:*`)
- **env:** telemetry is on iff `OTEL_EXPORTER_OTLP_ENDPOINT` is set (standard OTel env, http/protobuf, e.g. `http://alloy:4318`). `WCL_ENVIRONMENT` is `dev|ci|prod` and drives `deployment.environment.name` and the content policy. **Unset means the lockdown (content off)**: fail-safe; compose sets `dev` for the backend. Version: `WCL_GIT_SHA` if set, else `git rev-parse --short HEAD` if available, else `unknown`. Ansel puts these in `docker-compose.yml`.
- **content stream:** set the log attribute `app.content="true"` on any log record the backend emits that carries prompt, response or tool content; Alloy routes those (and GenAI `gen_ai.*` message events) to the 7-day content stream. If ADK emits content as log events under the latest-experimental semconv, say which event names on the board (key `contract:content-stream`) so Ansel routes them.
- The backend must start and serve normally when Alloy is unreachable (exporters fail quietly, no blocking at startup or per request).

## What this code must never allow (the security review will attack these)
- A secret (tokens, keys, cookies, DSNs, the WCL client secret, `Authorization` headers) in any exported span attribute, event or log record, with content on or off.
- Content leaving the process when `WCL_ENVIRONMENT` is not `dev`.
- Telemetry or instrumentors active in the test suite or when no endpoint is set; global instrumentation leaking between tests.
- The app blocking, slowing a turn noticeably, or crashing because the collector is down or slow.
- IDs (session, user, workspace, conversation) as metric labels.

## Tests and proof
- Use the in-memory span/log exporters; no network, no live model or WCL calls (fakes and fixtures).
- Prove each AC with a test; mutation-check the security ones (`mutate.py`): remove the redaction filter or flip the policy, and a test must fail.
- `check.py run --as nils` on the committed tree for the receipt. No Postgres-only work is expected; use `--pg nils` if you touch SQL behaviour.
- Live checks (team-lead runs them on the merged tip; board `question`, key `live-check:054`, exact steps): the real chat turn as one trace in Tempo with the stack up, a log line opening its trace, and the one-shot GenAI span for a real Claude and a real Gemini title call.

## Hand-off
Stories to Under Review, a board `handoff`, and your final result: branch, commits, files, the `check.py` RESULT and RECEIPT lines, risks, and an AC-by-AC mapping.
