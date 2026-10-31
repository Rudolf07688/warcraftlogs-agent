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
| S1' | Unchanged, except: our own `REPORT_SUMMARY` answered `reportData.report: null` offers a `ReportGone` **instead of** the response (and still raises / returns as before). With `errors`, only when every error has path `[reportData, report]` and reads as not-found/permission (041, scope:041:gone-rule). No other query text ever offers one. |
| S7 | With a source set, `query` awaits `source(query_key, query, variables)` in the **caller's** context before single-flight. Bytes → returned through `_loads` (no network, no sink offer). None or any exception → the normal network path. |
| S8 | No source set (CLI, evals, tests): one `is None` check, behaviour unchanged. |
| S9 | `exact_report_codes` is None for any `#`, any `report(` field it can't parse, or an unresolved, blank or padded code. Store reads use it. Report status comes only from `REPORT_SUMMARY` / `report_summaries_query` texts. |
| S10 | `returned_report_code` (041): the one code of a *plain* query (one `report` token, variable code, no `#`/`@`/`"`/`...`/`fragment`, no alias `:` outside arguments) when the body starts with `data[._cost].reportData.report = {…}`; else None. |

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
| W2' | The consumer writes up to 20 items and 8 MB per transaction; any failure, a timeout included, retries each item alone in order (041). |
| W3' | Failure logs name only the exception class and SQLSTATE. Pending throttled counts are logged on `stop`. |
| W6 | `offer` records the tenant of `current_identity` (None outside a signed-in turn). Grants come from the response (041, scope:041:grant-rule): a summary grants each code whose report came back with that code; any other query grants only `returned_report_code`. |
| W7 | A `ReportGone` (or a summary showing `private`) deletes every row naming the code and its status; the consumer then evicts `wcl:v1:report:<code>:*` from Redis outside the DB timeout (own 5 s bound). Rows the strict parser can't resolve are filed under every string literal / string variable too, so deletion finds them. |
| R1' | Same hash → only `fetched_at` moves forward; different hash → every column replaced (newer fetch only). |
