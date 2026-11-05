# Research: 059

## R1 405 becomes 500 (sc-461)
- Decision: wrap `opentelemetry.instrumentation.fastapi._get_route_details` (module global, looked up per request) and return `None` on AttributeError.
- Rationale: the crash is in the PARTIAL branch, which reads `.path` from FastAPI 0.141's lazily included `_IncludedRouter`, before our `server_request_hook` runs; the instrumentation has no option to replace it. Our hook still names the span by template.
- Alternatives: our own ASGI middleware instead of the instrumentor (much more code); pin an older FastAPI (no).

## R2 Board window (sc-463)
- Decision: accept. See spec Clarifications and board decision #19.
- Alternatives: raise `reject_old_samples_max_age` globally and widen `log_window` (admits old content records; per-tenant only).

## R3 Finish reasons
- Decision: app counter in the agent runner, fixed name set: stop, max_tokens, safety, recitation, language, blocklist, prohibited_content, spii, malformed_function_call, image_safety, unexpected_tool_call, too_many_tool_calls, other.
- Rationale: events are ADK `LlmResponse`s carrying `finish_reason` (`types.FinishReason`) for both providers (Anthropic `stop_reason` is mapped by ADK). Non-partial only (streamed partials may repeat it). `FINISH_REASON_UNSPECIFIED`/`None` not counted (ADK's `is_reported_finish_reason`).
- Alternatives: spanmetrics dimension on `gen_ai.response.finish_reasons` (array attribute).

## R4 Conversation depth
- Decision: session-state counter `app_turns` (see Clarifications).
- Rationale: `_ensure_session` already loads the session (no events) and returns state; `Runner.run_async(state_delta=...)` attaches the delta to the user event, so it persists with the turn.
- Alternatives: count user events (loads the whole history, PERF-008); ws.py message count (outside the footprint, and the agent runner is where the turn ends).

## R5 Pyroscope
- Decision: `pyroscope-io==1.4.0` + `pyroscope-otel==1.1.0`; `pyroscope.configure(application_name="api", server_address=..., tags={service_namespace, deployment_environment_name, service_version})`; `PyroscopeSpanProcessor` added before the batch processor. Image `grafana/pyroscope`, pinned to an exact tag checked against the registry at implementation.
- Rationale: the processor tags samples of *root* spans (`span_id` tag) and sets `pyroscope.profile.id`; Grafana's Tempo `tracesToProfiles` opens the flame graph for that id.
- Limitation: thread tags are per OS thread; concurrent asyncio root spans share the event-loop thread, so overlapping requests can share samples. Fine for a one-user local app; documented.
