---
name: docker-compose-multi-service
description: |
  Use this skill when designing or maintaining Docker Compose setups for multi-service local development. Focuses on service naming, networking, healthchecks, depends_on behavior, profiles, environment handling, bind mounts, restart behavior, and clean local-dev patterns for backend systems.
---

# Docker Compose Multi Service

## Use When

Use this skill for local multi-container development, especially when running several backend services together.

This is a local-dev and integration skill, not a Kubernetes replacement guide.

## Core Rules

- Keep one clear service per container.
- Use Compose service names as internal hostnames.
- Add healthchecks for important dependencies.
- Do not assume `depends_on` means a service is fully ready.
- Use profiles for optional dev tooling.
- Keep env handling explicit.
- Prefer simple, readable Compose files over clever YAML tricks.

## Service Naming

Use stable, descriptive service names.

Why:
- service names become internal DNS names,
- logs and debugging stay clearer,
- other containers can refer to them directly.

Good examples:
- `agent-orchestrator`
- `agent-langchain`
- `agent-adk`
- `agent-agno`
- `agent-gateway`
- `nats`
- `jupyter`

## Networking

Compose creates a shared network by default.

Recommended pattern:
- let services talk to each other by service name,
- avoid unnecessary host port exposure,
- only publish ports needed from the host.

Inside Compose, prefer:
- `http://agent-gateway:PORT`
- `nats://nats:4222`

Do not use `localhost` for inter-container calls.

## Healthchecks

Add healthchecks for services other services rely on.

Typical candidates:
- API services,
- gateway,
- NATS,
- notebook or dev tooling if relevant.

Healthchecks should verify useful readiness, not just that the process exists.

Good examples:
- HTTP endpoint check for API containers,
- protocol-aware ping for infrastructure when practical.

## `depends_on`

Use `depends_on` for startup ordering, not as a full readiness system.

Important rule:
- a container starting is not the same as the service being ready.

Recommended:
- combine `depends_on` with healthchecks where possible,
- still make applications resilient to temporary dependency unavailability,
- retry connections during app startup if needed.

Do not assume Compose alone solves readiness.

## Profiles

Use profiles for optional services.

Good profile use cases:
- Jupyter notebook,
- protocol inspector,
- debug UI,
- local-only helper tools.

This keeps the default stack smaller while allowing richer dev setups when needed.

## Environment Handling

Keep environment configuration explicit and consistent.

Recommended:
- use `.env` for shared local values,
- use `environment:` for small explicit settings,
- use `env_file:` when many variables belong together,
- document required variables clearly.

Do not spread critical config across many hidden files without documentation.

## Volumes and Bind Mounts

Use bind mounts for fast local iteration on source code.

Recommended pattern:
- mount source into app containers during development,
- avoid mounting over critical built artifacts accidentally,
- keep persistent data in named volumes where appropriate.

Typical named volume uses:
- notebook state,
- local databases,
- broker persistence when needed.

## Build vs Image

Use `build:` for local development of services you are actively editing.

Use `image:` when:
- consuming a third-party service,
- using a stable prebuilt internal image,
- you do not need to rebuild locally.

A mixed Compose file is normal.

## Restart Behavior

Use restart policies intentionally.

Recommended:
- infrastructure services often benefit from restart behavior in dev,
- application services should fail visibly when configuration is broken.

Do not hide broken startup loops behind aggressive restart policies.

## Logs

Compose is part of your debugging workflow.

Recommended:
- keep service names clean for readable logs,
- ensure each container logs to stdout/stderr,
- avoid burying logs in files inside containers.

A good Compose setup should make `docker compose logs` useful immediately.

## Project Layout

A clean pattern is:

```text
compose.yaml
.env
services/
  orchestrator/
  agent-adk/
  agent-agno/
  agent-langchain/
```

Optional:
- `compose.override.yaml` for local overrides,
- profile-based optional services instead of many separate Compose files.

## Recommended Pattern For This Project

A good Compose layout for this project is:
- orchestrator or chat backend service,
- three agent services,
- one MCP service,
- one NATS service,
- one agent gateway service,
- optional `jupyter` profile.

Use profiles for tooling, not for core runtime dependencies.

## Common Pitfalls

- Using `localhost` between containers.
- Relying on `depends_on` without healthchecks or retries.
- Publishing every port to the host unnecessarily.
- Hiding config in too many places.
- Mounting volumes that overwrite container runtime files accidentally.
- Putting too much logic in Compose instead of the services themselves.
- Creating many environment-specific Compose files too early.

## Review Checklist

1. Are service names stable and descriptive?
2. Are inter-container calls using service DNS names?
3. Are important dependencies healthchecked?
4. Is `depends_on` used with the right expectations?
5. Are optional tools moved into profiles?
6. Is env handling understandable?
7. Are mounts safe for local development?
8. Are only necessary ports exposed?
9. Are restart policies intentional?
10. Are logs easy to inspect with Compose commands?

## Defaults

- Stable service names.
- Internal DNS via service name.
- Healthchecks on important dependencies.
- `depends_on` for ordering, not magical readiness.
- Profiles for optional tooling.
- Clear env configuration.
- Bind mounts for active dev services.
- Named volumes for persistent state where needed.
- Minimal published host ports.
