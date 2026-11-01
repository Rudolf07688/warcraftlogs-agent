# Fetch source (wcl_client ↔ backend)

```python
@dataclass(frozen=True)
class StoredFetch:
    content: bytes
    shared: bool        # every code public: may go to the shared Redis cache

class FetchSource(Protocol):
    async def __call__(self, query_key: str, query: str, variables: dict[str, Any]) -> StoredFetch | None: ...
    def scope(self) -> str: ...   # whose visibility the answer depends on (tenant id or "")
```
- Called once per single-flight inside a lane slot, before the 429 block check; failures are misses.
- A stored answer makes no network call, logs no cost, is not offered to the sink, and does not mark
  the turn as external. When `shared` is false each waiter marks its load unshareable.
- `FetchedResponse.requested_at`: request start (first attempt), used to order against ReportGone.
- `store_batch` → `BatchResult(gone, changed)`; `upsert_raw_fetch` → `bool` (payload changed).
