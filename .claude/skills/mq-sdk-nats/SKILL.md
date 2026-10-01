---
name: nats-python-agent-backbone
description: |
  Use this skill when designing or implementing NATS in Python for agent backends, especially where NATS is the ingestion and event backbone around A2A-based orchestration. Covers Core NATS versus JetStream, subject design, async nats.py patterns, request-reply, queue groups, durability decisions, and project-specific guidance for publisher -> NATS -> master/orchestrator -> A2A workers.
---

# NATS Python Agent Backbone

## Purpose

Use this skill when building or reviewing a Python system that uses NATS as the messaging backbone for an agent backend.

This skill is specifically optimized for architectures where:
- a publisher sends work into NATS,
- a master or orchestrator service consumes that work,
- the orchestrator delegates to worker agents over A2A,
- NATS is the event and ingestion layer rather than the agent-to-agent protocol.

This is not a generic NATS encyclopedia. It is an opinionated implementation skill for agent systems.

## Core Decision Model

Treat NATS as **the event transport and coordination backbone**, not as a replacement for A2A.

Recommended split:
- **NATS** handles event ingestion, fan-out, decoupling, lightweight service messaging, and optional durability.
- **A2A** handles agent-to-agent task delegation and long-running task semantics.
- **MCP** handles agent-to-tool communication.

Do not blur these layers unless there is a deliberate reason.

## Primary Architecture Pattern

Preferred project pattern:

```text
publisher -> NATS -> master/orchestrator -> A2A worker agents
```

Recommended responsibilities:
- publisher publishes new work requests,
- NATS transports those requests,
- master/orchestrator subscribes and decides what to do,
- master/orchestrator owns canonical task identity and task state,
- master/orchestrator delegates real agent work over A2A,
- downstream completion may be emitted back onto NATS and/or to a webhook.

Important rule:
Use NATS to move events between services. Use A2A when one autonomous agent needs another autonomous agent to perform work.

## Task State Authority

NATS events are not the source of truth for task state.

Recommended rules:
- orchestrator creates the canonical `task_id`,
- NATS payloads carry that `task_id` and correlation metadata,
- downstream agent-local task IDs remain secondary references,
- completion events on NATS are notifications, not authoritative state,
- webhook receivers and clients should reconcile against orchestrator-owned state.

Do not treat a message bus as the canonical task store.

## Start With Core NATS

Default to **Core NATS first**.

Use Core NATS when:
- you need lightweight pub/sub,
- you need low-latency request/reply,
- the system can tolerate at-most-once delivery,
- you do not need replay,
- you do not need durable consumers,
- you want the simplest operational shape.

This is the preferred starting point for your dev phase.

Do not introduce JetStream immediately unless you have a concrete reason.

## When To Add JetStream

Add **JetStream** only when you need persistence-oriented messaging semantics.

Use JetStream when you need:
- message durability,
- replay,
- consumer acknowledgements,
- redelivery,
- consumer lag tracking,
- recovery after subscriber downtime,
- auditability of task ingress or task completion events.

Project recommendation:
- start with Core NATS for local development and orchestration validation,
- add JetStream once you need reliability guarantees for production ingestion or event recovery.

## Subject Design

Design subjects intentionally. They are part of your system contract.

Recommended rules:
- use dot-delimited subjects,
- keep them short but expressive,
- encode domain meaning rather than implementation detail,
- avoid random ad hoc subject names,
- document subject ownership and payload schema.

Suggested taxonomy for this project:

```text
tasks.incoming
tasks.accepted
tasks.failed
tasks.completed
agents.master.events
agents.master.errors
notifications.webhook
```

If you later partition by tenant or environment, use prefixes consistently:

```text
dev.tasks.incoming
prod.tasks.incoming
prod.notifications.webhook
```

Do not put large routing logic into the subject name unless it is a stable domain concern.

## Payload Design

Use JSON payloads with a stable schema.

Recommended message fields for incoming work:
- `task_id`
- `objective`
- `submitted_at`
- `source`
- `tenant_id` if needed
- `correlation_id`
- `metadata`
- `reply_to` only when request/reply is intentional

Example payload:

```json
{
  "task_id": "task-001",
  "objective": "Summarize the uploaded document and extract action items.",
  "submitted_at": "2026-06-11T10:00:00Z",
  "source": "publisher",
  "correlation_id": "corr-001",
  "metadata": {
    "priority": "normal",
    "tenant_id": "acme"
  }
}
```

Rules:
- keep payloads explicit,
- avoid hidden assumptions,
- keep correlation identifiers stable across NATS, A2A, and webhook boundaries,
- version schemas when they become shared contracts.

## Python Client Pattern

Use the official `nats.py` client and keep the system async end-to-end.

Recommended lifecycle:
1. create one connection for the process,
2. connect during startup,
3. keep subscriptions registered for process lifetime,
4. use async callbacks for subscribers,
5. drain gracefully on shutdown,
6. close cleanly.

Do not open a new NATS connection per message.

## Connection Management

Recommended rules:
- create one shared NATS connection per service process,
- reconnect automatically using client defaults where appropriate,
- log connection loss and reconnect events,
- treat connection state as part of service health,
- use graceful drain before exit.

If the orchestrator depends on NATS for ingress, the health model should distinguish:
- app process healthy,
- NATS connected,
- subscriptions active.

## Subscriber Pattern

For the master/orchestrator service, use a long-lived subscription callback.

Pattern:
- subscribe to `tasks.incoming`,
- parse payload,
- validate required fields,
- map to internal request model,
- invoke orchestration logic,
- publish acceptance or failure events if needed,
- acknowledge only if using JetStream.

Keep the subscription callback thin.

Recommended structure:
- subscription callback parses and hands off,
- business logic lives in orchestrator service functions,
- error handling publishes structured failure events.

Do not implement the full orchestration pipeline inline inside the raw NATS callback.

## Publisher Pattern

A publisher should be boring and deterministic.

Rules:
- construct one clear JSON payload,
- publish to a documented subject,
- include task and correlation IDs,
- do not embed transport-specific quirks into business payloads,
- flush only when needed for delivery certainty in critical flows.

For development, the publisher can be:
- a notebook cell,
- a CLI script,
- a curl-like test harness,
- a minimal FastAPI endpoint.

## Queue Groups

Use **queue groups** when multiple instances of the same service should share a workload.

In this architecture, queue groups are appropriate when:
- multiple orchestrator replicas consume from `tasks.incoming`,
- only one replica should handle each message.

Use queue groups for horizontal scaling of a service class, not for arbitrary routing semantics.

Do not confuse queue groups with business workflow partitioning.

## Request-Reply Pattern

NATS request-reply is useful, but should be used intentionally.

Use request-reply when:
- you need a quick synchronous service response,
- the operation is short-lived,
- you want a lightweight RPC pattern,
- there is a clear single responder.

Do not use request-reply for:
- long-running agent tasks,
- workflows that require status transitions,
- anything better represented as an A2A task.

Project rule:
- use request-reply only for lightweight operational queries or small helper services,
- do not use it as a substitute for A2A delegation.

## Core NATS vs A2A

Use this decision table:

- **Need to ingest work into the system?** Use NATS.
- **Need to notify another service of an event?** Use NATS.
- **Need one agent to delegate autonomous work to another?** Use A2A.
- **Need task lifecycle, artifacts, or clarification loops?** Use A2A.
- **Need a fast one-hop service response?** Maybe NATS request-reply.
- **Need durable event history or replay?** Use JetStream.

## JetStream Pattern

When adding JetStream, define streams and consumers around business durability requirements.

Recommended uses in this project:
- persist inbound task requests,
- persist task completion events,
- replay historical task traffic during debugging,
- recover after orchestrator downtime.

Recommended rules:
- keep stream names aligned with domain meaning,
- use explicit retention and limits,
- define consumer ack behavior intentionally,
- document redelivery semantics clearly.

Do not add JetStream merely because it exists.

## Ack and Redelivery Guidance

If using JetStream consumers:
- understand when a message is considered processed,
- ack only after the orchestrator has safely recorded or handed off work to the next trusted stage,
- plan for duplicate delivery,
- make handlers idempotent.

Idempotency rule:
if the same ingress message is delivered twice, the system should not create two logically separate tasks unless that is explicitly desired.

Recommended idempotency keys:
- `task_id`
- `correlation_id`
- publisher-generated message identity

## Completion Events

When work completes, decide whether completion should be represented on NATS, a webhook, or both.

Recommended pattern for this project:
- webhook notifies the web application or external system,
- optional NATS completion event notifies internal subscribers.

Example subjects:

```text
tasks.completed
tasks.failed
notifications.webhook
```

Use NATS completion events when:
- internal observability consumers exist,
- audit or analytics pipelines need the event,
- other services react to completion.

Remember: completion events are notifications, not the authoritative task record.

## Orchestrator Integration Pattern

The orchestrator is the NATS consumer and A2A client.

Recommended flow:
1. receive message from NATS,
2. validate and normalize payload,
3. create or load canonical orchestration state,
4. choose downstream A2A worker(s),
5. submit A2A task(s),
6. track downstream task IDs as secondary references,
7. on completion, update canonical state,
8. emit webhook and optionally publish completion event.

Important rule:
Do not let worker agents subscribe directly to broad ingress subjects unless that is a deliberate competing-consumer design. Keep orchestration decisions centralized in the master during this project.

## Async Python Pattern

Keep everything asyncio-native.

Recommended service structure:
- FastAPI startup hook creates NATS connection,
- FastAPI shutdown hook drains and closes it,
- subscriber callback dispatches to async orchestration function,
- orchestration function performs A2A calls using async HTTP clients.

Avoid threading unless you must integrate with a blocking dependency.

## Graceful Shutdown

Always drain before exit.

Recommended shutdown order:
1. stop accepting new HTTP requests if applicable,
2. drain NATS subscriptions,
3. wait for in-flight message handlers to finish if possible,
4. close NATS connection,
5. shut down app process.

This matters especially when the orchestrator bridges ingress events to long-running downstream tasks.

## Error Handling

Design explicit failure paths.

Possible failure categories:
- invalid payload,
- NATS unavailable,
- no subscriber or no responder in request-reply flows,
- orchestrator exception,
- downstream A2A call failure,
- duplicate message,
- JetStream redelivery loop.

Recommended handling:
- log structured error with correlation IDs and canonical task IDs,
- publish failure event if appropriate,
- avoid swallowing exceptions silently,
- distinguish transport failure from business failure.

If using request-reply, handle "no responders" explicitly rather than as a generic timeout.

## Observability

At minimum, log these fields consistently:
- subject,
- task_id,
- correlation_id,
- publisher/source,
- consumer group if applicable,
- downstream A2A task IDs,
- final outcome.

Recommended metrics:
- messages received per subject,
- processing duration,
- failed messages,
- duplicate suppressions,
- reconnect count,
- queue depth or consumer lag if using JetStream.

## Testing Guidance

Test at three layers.

### 1. Subject and Schema Tests
- verify publishers send expected subjects,
- verify payloads conform to schema,
- verify correlation IDs are preserved.

### 2. Consumer Logic Tests
- orchestrator correctly parses ingress,
- invalid messages fail safely,
- routing decisions are deterministic when required,
- completion events are emitted correctly.

### 3. Integration Tests
- local NATS container is reachable,
- end-to-end publish -> consume -> A2A delegate works,
- duplicate or redelivered messages do not corrupt state,
- graceful shutdown drains cleanly.

## Common Gotchas

### 1. Using NATS where A2A should be used
Do not replace task-oriented agent delegation with raw pub/sub just because it is available.

### 2. Introducing JetStream too early
Start simple. Add durability only when a real requirement appears.

### 3. Opening a new connection per operation
Use one shared process-level connection.

### 4. Embedding business logic inside subscription callbacks
Keep callbacks thin and dispatch to service functions.

### 5. Missing idempotency planning
If messages can replay or redeliver, duplicates must be harmless.

### 6. Weak subject naming
Subjects become architecture. Name them carefully.

### 7. Losing correlation IDs across boundaries
Keep identifiers intact from publisher through orchestrator to A2A and webhook completion.

### 8. Treating request-reply as a long-running workflow tool
It is not a substitute for lifecycle-aware task protocols.

### 9. Ignoring graceful drain on shutdown
This causes dropped in-flight work.

### 10. Treating NATS events as the system of record
Use orchestrator-owned task state as the source of truth.

## Recommended Engineering Rules

Use these rules consistently:
- Start with Core NATS.
- Add JetStream only for explicit durability needs.
- Use stable dot-delimited subject names.
- Keep one async NATS connection per process.
- Keep subscriber callbacks thin.
- Preserve task and correlation IDs everywhere.
- Use queue groups only for shared service scaling.
- Use request-reply only for short-lived synchronous interactions.
- Keep NATS as the ingress/event layer and A2A as the delegation layer.
- Orchestrator owns canonical task IDs and task state.
- Design handlers to survive duplicates and reconnects.
