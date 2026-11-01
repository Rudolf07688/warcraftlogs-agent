# Contract: knowledge base indexer (hooks)

Module `backend/app/kb/indexer.py`. One `KbIndexer` per process, started and stopped by the app
lifespan. Every `offer_*` is O(1), never awaits, never raises, and is a no-op when no indexer is
running (CLI, evals, most tests).

```python
@dataclass(frozen=True)
class GuideJob:      # from the publish hook
    guide_id: uuid.UUID; class_name: str; spec: str; content_type: str
    markdown: str; patch: str | None

@dataclass(frozen=True)
class ExchangeJob:   # from the chat turn
    tenant_id: uuid.UUID; conversation_id: uuid.UUID; message_seq: int
    question: str; answer: str; created_at: datetime

def offer_fetch(fetched: FetchedResponse) -> None    # writer, after commit, changed items only
def offer_guide(job: GuideJob) -> None              # guide pipeline, after the publish commit
def offer_exchange(job: ExchangeJob) -> None        # ws.py, after the final answer is saved
```

## Call sites (Gate 2 grants)

| Hook | File | Where | Condition |
|---|---|---|---|
| fetch | `backend/app/services/fetch_persistence.py` | after the batch commit, from `BatchResult.changed` (contract 5) | inside `offer_fetch`: `exact_report_codes(query, variables)` non-empty and `chunkable_query(query)` (a summary or `table` query); the queued `FetchJob` holds key, query, variables and codes only, and the consumer re-reads the stored body (P7 043 SEC-001) |
| guide | `backend/app/services/guide_pipeline/__init__.py` `_run` | after `publish_spec_guide` + commit | published only (held / failed never) |
| exchange | `backend/app/api/ws.py` `_handle_turn` | after the final `add_message` transaction closes | completed turn with streamed text; never on partial / error / rate-limit paths |
| lifecycle | `backend/app/main.py` `lifespan` | start next to the fetch writer; stop before `engine.dispose()` | `settings.kb_index_enabled` |

## Consumer behaviour

- Queue bounded by `kb_index_queue_max`; a full queue drops the job and logs a throttled
  warning (recovered by the backfill: `backlog:kb-dropped-jobs`).
- Each job: chunk (WCL parse off the loop above 256 kB), then one short transaction:
  - fetch / guide: `replace_source_chunks` (global table), also with no drafts, so a body that
    now yields none drops its old chunks (P7 SEC-002a). An FK failure (fetch deleted or
    report gone meanwhile) drops the job quietly.
  - exchange: under `tenant_scope(job.tenant_id)`: mentioned characters, then upsert the chat
    chunk; the composite FK refuses a conversation of another tenant or one deleted meanwhile.
- Then the pending rows written by that job are embedded (`RETRIEVAL_DOCUMENT`) in batches of
  `kb_embed_batch`; a vector is stored only where `content_hash` still matches. On any embed
  failure: log class only, keep NULL, pause embedding until the next sweep.
- Every `kb_embed_sweep_s` with no job: embed all NULL rows (global, then chat per tenant under
  its scope), until done or a failure.
- `stop(grace_s)`: stop accepting, drain within the grace, cancel.
- No chunk read here serves a user (FR-015).
