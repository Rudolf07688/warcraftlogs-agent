# Contract: Async Warcraft Logs Client and Lanes (side mission)

**Feature**: 013-welcome-recent-raids · QA PERF-201 and PERF-211

This is an internal module contract for `wcl_agent/wcl_client.py`, the only WCL client (Principle I). The `wcl_agent` package stays standalone, with no backend imports.

---

## Public surface

```python
def get_async_client() -> AsyncWCLClient
    """The client for the running event loop (one per loop, created lazily). It must be called on the loop.
    The sync get_client() bridge facade remains until Phase C. Then only get_async_client() is left."""

async def aclose_clients() -> None
    """Close the clients and HTTP pools of all loops. Called from the FastAPI lifespan shutdown."""

class AsyncWCLClient:
    async def query(self, query: str, variables: dict | None = None, *, cache: bool = True) -> dict
    """Run a GraphQL query and return its payload (a fresh dict, owned by the caller)."""

@contextmanager
def background_lane() -> Iterator[None]
    """Run WCL calls in this context in the background lane."""

async def acheck_rate_limit() -> dict   # the sync check_rate_limit() is removed in Phase C
```

---

## Behaviour that `query()` guarantees

| # | Guarantee | Requirement |
|---|---|---|
| G1 | No blocking I/O. Every network call is an `await` on `httpx.AsyncClient`. | FR-018 |
| G2 | **Cache**: a hit returns `json.loads(stored_bytes)`, a fresh object on every call (payloads over 256 KB are parsed with `asyncio.to_thread`). A miss stores `resp.content` (bytes) with the existing `ttl_for` rules. `rateLimitData` and `cache=False` skip the cache. | FR-022 |
| G3 | **Single-flight**: concurrent identical cache keys share one fetch task. Each caller `await`s `asyncio.shield(task)`. | FR-022 |
| G4 | **Cancellation**: a cancelled caller stops waiting at once. The shared task is cancelled only when its last waiter has gone, which frees its slot. | FR-019, SC-007 |
| G5 | **Timeout**: each fetch is bounded by `asyncio.timeout(WCL_QUERY_TIMEOUT_S=75)` around the slot plus the request. HTTP timeouts are `connect=5`, `read=60`. A timeout raises `TimeoutError` to every waiter and frees the slot. | FR-021 |
| G6 | **Lanes**: every fetch holds a `LaneLimiter` slot (below) for the length of the HTTP request only, not while waiting for single-flight or parsing a cache hit. | FR-020 |
| G7 | **Errors**: an HTTP error status raises `httpx.HTTPStatusError`. A GraphQL `errors` payload raises `RuntimeError(json)`, as today. Errors are never cached. | FR-023 |
| G8 | **Auth**: the token is fetched once under an `asyncio.Lock` and shared across loops by client id. A `401` refreshes the token once and retries. | FR-023 |
| G9 | **Tenant scope**: cache keys still include the `_scope_prefix` ContextVar (feature 006). It now propagates naturally through `await`. | FR-022 |

## `LaneLimiter`

```python
class LaneLimiter:
    def __init__(self, total: int, background_cap: int): ...
    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]: ...   # lane read from the wcl_lane ContextVar
```

| Rule | |
|---|---|
| L1 | `interactive` acquires when `in_use < total`. |
| L2 | `background` acquires only when `in_use < total` **and** `bg_in_use < background_cap` **and** `interactive_waiting == 0`. |
| L3 | Waiters queue FIFO as futures. A release (synchronous, so a cancelled holder always frees its slot) hands free slots to the oldest waiters whose rule allows it. A cancelled waiter leaves the queue cleanly and wakes the others. |
| L4 | Settings: `WCL_MAX_CONCURRENCY` (default 6, as today) and `WCL_BACKGROUND_CONCURRENCY` (default 2, clamped to `1 … total-1`). |
| L5 | One limiter per event loop, so asyncio primitives are never shared across loops. Tests run several loops. |

## Lane assignment

| Caller | Lane |
|---|---|
| Chat agent tools (all `TOOLS`) | interactive (default) |
| `services/raids.capture_raid` metadata lookup (inside a chat turn) | interactive |
| `services/guide.resolve_active_spec` | **background** |
| `patch.current_patch` from `ws.py` (preamble) and `api/guides.py` | **background** |
| `services/recent_raids` list and detail steps | **background** (FR-024) |
| CLI `menu.select_encounter` | interactive (`async def`, awaited by `cli._main`) |

## Concurrency helpers in `wcl_agent/aio.py` (replace `gather_threads` for WCL)

```python
async def gather_settled(*aws: Awaitable[T]) -> list[T | BaseException]
    """asyncio.gather(..., return_exceptions=True), in input order. If the caller is cancelled, every child is cancelled too."""
```

`unwrap(result)` moves here unchanged: it re-raises a captured exception.

```python
def run_sync(coro: Awaitable[T]) -> T
    """For the Phase A–B transition only, in threading_utils. A sync caller on a tool-pool thread runs a converted async helper
    on the captured event loop with run_coroutine_threadsafe(...).result(). With no captured loop it uses asyncio.run. Deleted in Phase C."""
```

## Event-loop latency (SC-008)

- Large tool results are sized off the loop (`report_tools._acap`, a `to_thread` around `_cap`).
- The backend calls `gc.collect(); gc.freeze()` once startup has finished. A cyclic-GC walk of the startup heap, triggered by allocations from parsing large payloads, stalled the loop for about 80 ms. Frozen, it takes about 3 ms.
- Measured with `test_wcl_loop_lag.py` (4 turns, each looping over 1.3 MB lookups, 0.2–0.6 s latency, nothing cached): the worst stall is 15–35 ms, down from 157 ms. The rest is the JSON CPU of results that complete in the same instant. Getting reliably under 20 ms needs a faster JSON codec or no longer re-encoding results to size them.

## Removed at the end of the migration (Phase C)

`WCLClient` (sync facade), `get_client()`, sync `check_rate_limit()`, `threading_utils.run_sync`, `threading_utils.off_loop`, `run_in_tool_pool`, the `wcl-tool` thread pool, `gather_threads` (moved into `models.py` for its non-WCL probes), the `WCL_TOOL_THREADS` setting and the `requests` dependency, if nothing else uses it.

## Tool contract

Every function in `wcl_agent.agent.TOOLS` becomes `async def`, with **an unchanged name, docstring, parameters and return shape**. ADK builds identical tool declarations from them, so no prompt or provenance change is needed (FR-023). `build_agent` registers `TOOLS` directly instead of wrapping each one in `off_loop`.
