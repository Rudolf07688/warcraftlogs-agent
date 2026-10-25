# Contract: the WCL fetch sink and the fetch writer

## Client side (`wcl_agent.client.wcl_client`)

```python
@dataclass(frozen=True)
class FetchedResponse:
    query_key: str
    query: str
    variables: dict[str, Any]
    content: bytes
    fetched_at: datetime

FetchSink = Callable[[FetchedResponse], None]

def set_fetch_sink(sink: FetchSink | None) -> None: ...
def operation_name(query: str) -> str | None: ...
def report_codes(query: str, variables: dict[str, Any]) -> list[str]: ...
```

| # | Guarantee |
|---|---|
| S1 | The sink is called **once per successful network call**: after HTTP success and with no GraphQL `errors`. Single-flight waiters never cause a second call. |
| S2 | Failed calls (HTTP error, GraphQL errors, timeout, cancellation, the PERF-004 fail-fast block) never call the sink. |
| S3 | The sink is called synchronously on the thread that ran the fetch. It must return quickly and must not raise. If it does raise, the exception is swallowed (debug log) and the fetch result is unaffected. |
| S4 | With no sink set (the default), the only cost is one `is None` check. |
| S5 | `wcl_agent` never imports backend or DB code. The backend installs the sink. |
| S6 | `report_codes` returns the `report(code: …)` arguments in query order, deduplicated, with whitespace stripped. `$var` arguments are resolved from `variables` and unresolved or empty values are skipped. `operation_name` returns `None` for anonymous queries. |

## Backend side (`backend.app.services.fetch_persistence`)

```python
class FetchWriter:
    def __init__(self, store: Callable[[FetchedResponse], Awaitable[None]] = store_fetch,
                 *, max_items: int, max_bytes: int) -> None: ...
    def start(self) -> None          # on the app loop: starts the task, installs the sink
    def offer(self, fetched: FetchedResponse) -> None   # the sink; O(1), never awaits
    async def stop(self, grace_s: float = 5.0) -> None
    dropped: int                     # total dropped (overflow + shutdown remainder)

async def store_fetch(fetched: FetchedResponse) -> None   # SessionLocal + upsert + commit
```

| # | Guarantee |
|---|---|
| W1 | `offer` never blocks or awaits. When the queue holds `max_items`, or `queued_bytes + len(content) > max_bytes`, the new response is dropped and counted, and one warning is logged per 60 s with the count. |
| W2 | One consumer task writes items in arrival order, one `store` call per item, each bounded by a 10 s timeout. |
| W3 | Any exception from `store` is caught and logged (throttled to one per 60 s with a count; the first at once). The writer continues. Nothing reaches the fetch caller. |
| W4 | `stop` first uninstalls the sink, then waits up to `grace_s` for the queue to drain, then cancels the task. Whatever was still waiting is counted as dropped and logged once. `stop` returns within `grace_s` plus a cancel round-trip. |
| W5 | `offer` called from a thread other than the writer's loop is marshalled with `call_soon_threadsafe`. |

## Repository (`backend.app.repositories.raw_fetches`)

```python
async def upsert_raw_fetch(session: AsyncSession, fetched: FetchedResponse) -> None
```

| # | Guarantee |
|---|---|
| R1 | One row per `query_key`. A newer `fetched_at` replaces every non-key column, and an older one is ignored. |
| R2 | The stored `payload` is the response body decoded by the database, without `data._cost`. |
| R3 | `report_codes` = `report_codes(query, variables)`; `report_code` is set only when that list has exactly one entry. |
| R4 | Executes the statement but does not commit: the caller owns the transaction, as in the other repositories. |
