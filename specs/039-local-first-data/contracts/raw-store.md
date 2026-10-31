# Contract: the raw WCL store (039)

Extends specs/020-fetch-persistence/contracts/fetch-sink.md. Changed guarantees are marked.

## Client (`wcl_agent.client.wcl_client`)

```python
@dataclass(frozen=True)
class ReportGone:                 # new: a fetch showed this report missing/private
    codes: tuple[str, ...]
    seen_at: datetime

FetchSink = Callable[[FetchedResponse | ReportGone], None]           # changed: union
FetchSource = Callable[[str, str, dict[str, Any]], Awaitable[bytes | None]]  # new
def set_fetch_source(source: FetchSource | None) -> None: ...        # new
def exact_report_codes(query, variables) -> list[str] | None: ...    # new: strict parse
```

| # | Guarantee |
|---|---|
| S1' | Unchanged, except: a single-report query whose response has `reportData.report: null` offers a `ReportGone` **instead of** the response (and still raises / returns as before). |
| S7 | With a source set, `query` awaits `source(query_key, query, variables)` in the **caller's** context before single-flight. Bytes → returned through `_loads` (no network, no sink offer). None or any exception → the normal network path. |
| S8 | No source set (CLI, evals, tests): one `is None` check, behaviour unchanged. |
| S9 | `exact_report_codes` is None for any `#`, any `report(` field it can't parse, or an unresolved/blank code. Grants, gone detection and store reads use only it. Report status comes only from `REPORT_SUMMARY` / `report_summaries_query` texts. |

## Backend

```python
# repositories/raw_fetches.py — the ONLY module that reads raw_fetches
async def read_visible_fetch(session, query_key: str, *, tenant_id: UUID | None, since: datetime,
                             fresh: Callable[[datetime, list[ReportStatus | None]], bool]
                             ) -> str | None
async def upsert_raw_fetch(session, fetched: FetchedResponse) -> None  # hash compare + upsert
async def grant_codes(session, tenant_id: UUID, codes: Sequence[str], at: datetime) -> None
async def record_report_status(session, statuses: Sequence[ReportStatus]) -> None
async def delete_report(session, code: str) -> int

# services/raw_fetch_reads.py
async def read_stored_fetch(query_key, query, variables) -> bytes | None   # the FetchSource

# services/fetch_persistence.py
@dataclass(frozen=True)
class PendingWrite: item: FetchedResponse | ReportGone; tenant_id: UUID | None
class FetchWriter(store: Callable[[Sequence[PendingWrite]], Awaitable[None]] = store_batch, ...)
```

| # | Guarantee |
|---|---|
| V1 | `read_visible_fetch` returns the payload only when the row is visible (data-model Rules) **and** `fresh(fetched_at, statuses)`; otherwise None. A guard test fails if another module selects from `RawFetch`. |
| V2 | `read_stored_fetch` returns None without touching the DB for a query naming no report; otherwise reads with the current identity's tenant (None → public only), bounded by 3 s; any error → None (debug log). |
| W2' | The consumer writes up to 20 items per transaction; a non-timeout failure retries each item alone. |
| W3' | Failure logs name only the exception class and SQLSTATE. Pending throttled counts are logged on `stop`. |
| W6 | `offer` records the tenant of `current_identity` (None outside a signed-in turn). A successful fetch grants its codes (≤ 32 chars) to that tenant. |
| W7 | A `ReportGone` (or a summary showing `private`) deletes every row naming the code and its status, after the batch commits evicts `wcl:v1:report:<code>:*` from Redis. |
| R1' | Same hash → only `fetched_at` moves forward; different hash → every column replaced (newer fetch only). |
