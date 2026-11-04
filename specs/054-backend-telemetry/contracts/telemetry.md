# Contract: backend telemetry (with 053)

## Environment (board `contract:env`)
| Var | Meaning |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | on iff set, e.g. `http://alloy:4318` (http/protobuf) |
| `WCL_ENVIRONMENT` | `dev` → content on; `ci`/`prod`/unset/other → lockdown |
| `WCL_GIT_SHA` | `service.version`; fallback `git rev-parse --short HEAD`, then `unknown` |

## Content stream (board `contract:content-stream`)
- Log records with content carry `app.content="true"`. The backend sets it on every `gen_ai.*`
  log event (ADK: `gen_ai.client.inference.operation.details` under the experimental semconv;
  `gen_ai.user.message`, `gen_ai.system.message`, `gen_ai.choice` under the stable one).
- Outside dev no `gen_ai.*` log event is exported.

## Spans
- Chat turn root: `chat turn` (SERVER, `http.route=/ws/chat`), children `invoke_agent …`,
  `generate_content …`, `execute_tool …`, httpx `POST`, SQLAlchemy, Redis spans.
- One-shot: `chat {model}` / `embeddings {model}` (CLIENT) with `gen_ai.*` metadata.
- Not traced: `/health`, `/api/health`, the `/ws/chat` connection itself.
