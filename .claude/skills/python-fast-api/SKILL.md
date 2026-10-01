---
name: fastapi-service-patterns
description: |
  Use this skill when building FastAPI services for backend systems, especially orchestrators, webhook receivers, internal APIs, and async service containers. Focuses on lifespan-managed resources, dependency injection, router structure, response models, health endpoints, background task boundaries, and production-safe async patterns.
---

# FastAPI Service Patterns

## Use When

Use this skill for FastAPI services that act as:
- orchestrators,
- webhook receivers,
- internal APIs,
- control-plane services,
- async backends with shared clients or connections.

Do not use this skill as a generic CRUD guide.

## Core Rules

- Use FastAPI for the HTTP/service boundary, not for hidden workflow logic.
- Create shared resources in app lifespan, not per request.
- Use dependency injection for access to shared clients, config, and services.
- Keep route handlers thin.
- Put business logic in service modules.
- Use `response_model` and typed request models consistently.
- Keep long-running workflows out of `BackgroundTasks`.

## App Structure

Prefer a clear module split:

```text
app/
  main.py
  api/
    routes_health.py
    routes_tasks.py
    routes_webhooks.py
  services/
  models/
  deps/
```

Recommended responsibilities:
- `main.py`: app creation, lifespan, router registration.
- `api/`: HTTP route definitions only.
- `services/`: orchestration and business logic.
- `models/`: Pydantic request/response schemas.
- `deps/`: dependency providers.

## Lifespan

Use FastAPI lifespan for process-level resources.

Good candidates:
- HTTP clients,
- NATS connections,
- A2A clients,
- database pools,
- config objects,
- shared service containers.

Create them once at startup and close or drain them on shutdown.

Do not create connection-heavy clients inside request handlers.

## Dependency Injection

Use dependencies to provide:
- config,
- auth context,
- shared service objects,
- reusable clients,
- request-scoped helpers.

Keep dependencies explicit and composable.

Do not hide major side effects inside dependencies.

## Route Design

Keep handlers small.

A good route should usually:
1. validate input,
2. call a service method,
3. map the result to a response model,
4. return clean HTTP semantics.

Do not embed orchestration logic, retries, or heavy branching directly in the route function.

## Models

Use Pydantic models for all external contracts.

Recommended:
- request models for JSON bodies,
- response models for stable output,
- explicit error shapes where useful,
- shared contract models for webhooks and task APIs.

Avoid returning raw dicts everywhere once the API becomes shared.

## Response Rules

- Use `response_model` on routes.
- Keep HTTP responses stable and explicit.
- Return IDs and state for async workflows.
- Separate transport response shape from internal service objects.

For long-running task submission, prefer returning:
- accepted status,
- task ID,
- correlation ID,
- optional polling location.

## BackgroundTasks

Use `BackgroundTasks` only for lightweight post-response work.

Good uses:
- send a small notification,
- write lightweight audit records,
- trigger a non-critical follow-up.

Do not use `BackgroundTasks` for:
- long-running agent execution,
- durable workflows,
- critical orchestration,
- anything that needs strong retry or recovery semantics.

For real long-running work, hand off to your orchestrator/task system.

## Health Endpoints

Provide at least:
- liveness endpoint,
- readiness endpoint.

Recommended behavior:
- liveness: process is up.
- readiness: dependencies needed for useful work are available.

If the service depends on NATS or downstream clients, readiness should reflect that.

## Webhooks

Webhook routes should be:
- narrow,
- authenticated or signed,
- idempotent,
- fast to acknowledge.

Recommended pattern:
- validate signature,
- parse payload,
- persist or enqueue work,
- return quickly.

Do not block webhook handlers on long downstream processing.

## Async Rules

- Keep handlers async when they await I/O.
- Do not call blocking libraries from async handlers.
- Reuse async clients.
- Apply timeouts at outbound I/O boundaries.
- Respect cancellation and shutdown.

## Errors

- Raise HTTP errors only at the API boundary.
- Keep domain errors in service logic and map them cleanly.
- Return consistent error responses.
- Log structured context with correlation IDs.

Avoid leaking internal exceptions directly to clients.

## Recommended Endpoints

For this type of project, common endpoints are:
- `/health/live`
- `/health/ready`
- `/tasks`
- `/tasks/{task_id}`
- `/webhooks/task-complete`

Keep operational routes separate from business routes.

## Review Checklist

1. Are shared clients created in lifespan?
2. Are route handlers thin?
3. Are contracts modeled with Pydantic?
4. Are response models explicit?
5. Are long-running tasks kept out of `BackgroundTasks`?
6. Are health endpoints meaningful?
7. Are webhooks fast and idempotent?
8. Are async routes free of blocking code?

## Defaults

- Lifespan for shared resources.
- Dependency injection for shared access.
- Thin routes, fat services.
- Pydantic models for all API contracts.
- `BackgroundTasks` only for lightweight follow-up work.
- Explicit readiness/liveness endpoints.
- Fast, verified, idempotent webhook handlers.
