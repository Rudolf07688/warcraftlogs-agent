---
name: asyncio-python
description: |
  Use this skill when designing, implementing, or reviewing asynchronous Python systems with asyncio. Focuses on production-safe async patterns for service backends: structured concurrency, cancellation, timeouts, queues, semaphores, graceful shutdown, avoiding blocking I/O, and lifecycle management for long-running async services.
---

# Asyncio Python

## Purpose

Use this skill when working on Python services or agent backends that rely on `asyncio`.

This skill is especially relevant for:
- async orchestration services,
- FastAPI or ASGI applications,
- A2A clients and servers,
- NATS consumers and publishers,
- webhook dispatchers,
- long-running background workers,
- systems that need safe concurrency and clean shutdown.

This is not a beginner tutorial. It is an implementation skill for production-oriented async Python.

## Core Model

Treat `asyncio` as a **cooperative concurrency runtime**.

Key implications:
- tasks only yield control at await points,
- blocking code stalls the event loop,
- cancellation is normal control flow,
- background tasks need ownership,
- shutdown must be designed explicitly.

Do not write async code as if it were threaded code with `await` sprinkled on top.

## Primary Rules

Use these rules by default:
- prefer structured concurrency,
- keep async call chains async end-to-end,
- wrap external I/O with timeouts,
- propagate cancellation cleanly,
- avoid fire-and-forget tasks unless they are owned and tracked,
- use bounded concurrency when calling external systems,
- clean up long-lived resources explicitly.

## Structured Concurrency

Prefer **`asyncio.TaskGroup`** for related concurrent work.

Use `TaskGroup` when:
- several child tasks belong to the same parent operation,
- failure of one task should affect the group,
- lifecycle should end when the parent scope ends,
- cancellation and error propagation need to be predictable.

Why:
- it gives explicit ownership,
- it reduces orphaned task leaks,
- exceptions propagate more cleanly than scattered `create_task()` usage.

Avoid spawning loose tasks throughout the codebase without a clear owner.

## `create_task()` Guidance

Use `asyncio.create_task()` only when there is a clear ownership model.

Valid uses:
- a managed background supervisor keeps references,
- a service startup hook launches a known long-lived task,
- a parent component stores the task and handles cancellation on shutdown.

Invalid uses:
- creating a task and discarding the handle,
- creating background tasks in request handlers without lifecycle control,
- assuming the interpreter will clean things up correctly.

Rule:
Every created task should have an owner responsible for:
- tracking it,
- handling its errors,
- cancelling it on shutdown if needed.

## Cancellation

Treat cancellation as expected behavior, not as an exceptional edge case.

Important rules:
- cancellation is delivered via `CancelledError`,
- cleanup code may catch `CancelledError` briefly,
- after cleanup, let cancellation propagate unless there is a deliberate reason not to,
- never swallow cancellation silently.

Good pattern:
- acquire resource,
- run work,
- on cancellation, clean up,
- re-raise or allow the cancellation to continue.

Bad pattern:
- `except Exception:` that unintentionally swallows cancellation,
- logging cancellation as an application error,
- retry loops that ignore cancellation and keep running.

## Timeouts

Put explicit timeouts around external boundaries.

Use timeouts for:
- HTTP calls,
- A2A requests,
- NATS request-reply operations,
- database queries when relevant,
- webhook calls,
- long-running waits on queues or events when a bound matters.

Preferred approach:
- use `asyncio.timeout()` around a block of awaited work,
- keep the timeout close to the operation boundary,
- log timeout context with correlation IDs.

Do not rely on implicit or infinite waits for network operations.

## Blocking Work

Never run blocking I/O or CPU-heavy work directly on the event loop.

Danger signs:
- synchronous HTTP clients inside async handlers,
- file operations that may block heavily,
- CPU-heavy parsing or transforms inside coroutines,
- expensive cryptography or compression inline,
- third-party libraries that look async-friendly but are not.

When blocking work is unavoidable:
- use `asyncio.to_thread()` for blocking I/O adapters,
- move CPU-bound work to a worker process or external service,
- isolate legacy sync code at explicit boundaries.

Rule:
If a function blocks for real time without `await`, it is event-loop poison.

## Bounded Concurrency

Limit concurrency when calling external systems.

Use:
- `asyncio.Semaphore` when many tasks call the same external dependency,
- `asyncio.Queue` to buffer work between producers and consumers,
- explicit worker counts for background processing pipelines.

Why:
- protects downstream services,
- avoids connection storms,
- reduces memory growth,
- gives clearer backpressure behavior.

Do not use unbounded `gather()` over large input sets unless the workload is known to be small and safe.

## Queues

Use `asyncio.Queue` when work needs to move between async producers and consumers inside one process.

Good use cases:
- internal event pipelines,
- batching workers,
- separating ingress from processing,
- smoothing bursts.

Rules:
- define queue ownership clearly,
- define worker shutdown behavior,
- decide what should happen when the queue is full,
- avoid unbounded queues for untrusted or bursty input.

For long-running services, think through:
- queue size,
- draining behavior,
- cancellation of workers,
- fate of in-flight items at shutdown.

## `gather()` Guidance

Use `asyncio.gather()` for independent concurrent operations when you need the results together.

Good uses:
- a small set of parallel HTTP calls,
- parallel independent reads,
- fan-out work where all results matter.

Be careful with:
- very large lists of coroutines,
- mixed criticality tasks,
- hidden partial-failure semantics.

Prefer `TaskGroup` when:
- you need clearer structure,
- you are creating tasks inside a scope,
- cancellation and exception behavior should be more explicit.

## Resource Lifecycle

Manage long-lived async resources explicitly.

Examples:
- HTTP clients,
- websocket clients,
- database pools,
- NATS connections,
- A2A client sessions,
- background worker tasks.

Recommended pattern:
- create resources during startup,
- inject or pass them explicitly,
- close or drain them during shutdown,
- do not recreate them per request unless required.

Async context managers are preferred where possible.

## Graceful Shutdown

Shutdown is part of the design.

Recommended shutdown flow:
1. stop accepting new work,
2. signal background tasks to stop,
3. cancel or drain active tasks in an orderly way,
4. wait for cleanup with a bounded timeout,
5. close external resources.

A good async service should be able to explain:
- what tasks exist,
- who owns them,
- how they are stopped,
- what happens to in-flight work.

## Background Tasks

Background tasks need clear semantics.

Questions every background task should answer:
- who starts it,
- who stops it,
- what happens if it fails,
- how is failure observed,
- should it restart,
- does it own a queue or consume shared state.

Do not hide critical business logic in ad hoc background tasks started from request handlers.

For important long-lived loops, prefer a named supervisor component.

## Long-Running Loops

Long-running async loops are valid, but they must be cooperative and cancellable.

Rules for loops:
- await regularly,
- check for shutdown state if needed,
- do not spin without sleep or I/O,
- keep error handling explicit,
- do not trap the loop in an eternal retry without backoff.

A long-running loop should have:
- bounded retry strategy,
- cancellation support,
- clear ownership,
- observable health signals.

## Retries

Retries need control.

Recommended rules:
- retry only for transient failures,
- use bounded attempts or bounded time windows,
- apply backoff,
- honor cancellation during retry sleeps,
- log retry reason and context.

Do not retry blindly inside nested async layers where timeouts and retries multiply unpredictably.

## Debugging and Development

Use asyncio's debugging tools when behavior is suspicious.

Good practices:
- enable debug mode when investigating task leaks or slow callbacks,
- watch for warnings about un-awaited coroutines,
- inspect pending tasks during shutdown issues,
- look for blocking sync calls in hot async paths.

Common warning signs:
- tasks destroyed while pending,
- event loop blocked unexpectedly,
- coroutines created but never awaited,
- shutdown hangs because background tasks were never cancelled.

## Error Handling

Handle errors at the right level.

Rules:
- catch exceptions where you can add context or recover meaningfully,
- let failures propagate when the parent scope should decide,
- do not wrap every coroutine in giant broad exception blocks,
- keep correlation IDs and task context in logs.

For grouped work:
- decide whether one child failure should fail the whole parent,
- use structured concurrency to make that behavior explicit.

## Integration Patterns

### FastAPI / ASGI

Recommended pattern:
- create shared async resources during app startup,
- store them in application state or dependency providers,
- close them on shutdown,
- avoid creating connection-heavy clients inside request handlers.

### NATS

Recommended pattern:
- create one shared connection per process,
- register subscriptions during startup,
- drain on shutdown,
- keep callbacks thin and hand off to service logic.

### A2A / HTTP clients

Recommended pattern:
- reuse async HTTP clients,
- apply request timeouts,
- bound fan-out concurrency,
- preserve cancellation and correlation IDs.

## Anti-Patterns

Avoid these patterns:
- blocking libraries inside async code,
- `time.sleep()` in coroutines,
- untracked `create_task()` calls,
- swallowing `CancelledError`,
- unbounded fan-out with `gather()`,
- creating one network client per request without reason,
- infinite retries without backoff,
- startup code that launches tasks with no shutdown path,
- broad `except Exception` in cancellation-sensitive code,
- assuming async automatically means scalable.

## Review Checklist

When reviewing async Python code, check these in order:
1. Are there blocking calls on the event loop?
2. Are timeouts applied to external I/O?
3. Is concurrency bounded where needed?
4. Are created tasks owned and tracked?
5. Is cancellation handled cleanly?
6. Are long-lived resources reused and cleaned up?
7. Does shutdown have an explicit path?
8. Do background workers have supervision?
9. Are retries bounded and cancellable?
10. Are logs contextual enough to debug task behavior?

## Recommended Engineering Rules

Use these defaults unless there is a strong reason not to:
- prefer `TaskGroup` for scoped concurrent work,
- use `asyncio.timeout()` at network and service boundaries,
- use semaphores for high fan-out dependencies,
- use queues for internal backpressure,
- keep one shared client/connection per process where appropriate,
- make cancellation and shutdown first-class concerns,
- isolate blocking code explicitly,
- never fire-and-forget important work.

## Best Fit Use Cases

This skill is well suited for creating or reviewing:
- async orchestration backends,
- FastAPI services with background workers,
- NATS-connected Python services,
- A2A clients and servers,
- webhook dispatchers,
- internal event pipelines,
- long-running async service processes.
