# Contract: backfill CLI (sc-113)

```
uv run python -m backend.cli.kb_backfill [--kinds wcl,guide,chat] [--confirm] [--limit N]
```

Runs as the app's runtime role (`DATABASE_URL`), never at startup.

- **Dry run** (no `--confirm`): chunks every source that has no chunks yet in memory, adds the
  existing rows with a NULL vector, and prints one line per kind plus a total:
  `wcl: 1,234 chunks to embed, ~0.31M tokens, ~USD 0.05` — writes nothing, calls no embedder.
- **Confirmed**: per kind, page through sources without chunks, write their chunks (one
  transaction per source), then embed every NULL row in batches through the same embed code
  as the indexer. Exits non-zero when the embedder is unavailable (after writing the chunks,
  which stay keyword-searchable).
- **Resumable**: sources with chunks are skipped, rows with a vector are never re-embedded, so
  an interrupted run continues where it stopped.
- **Sources**: `wcl` = stored fetches naming a report (summaries first, so table chunks can copy
  fight metadata), via `raw_fetches.list_fetch_keys` (keyset pages, summaries first) + `raw_fetches.load_fetch_for_index` (one row at a time), skipping keys that already have chunks; ambiguous
  stored tables are skipped (#35). `guide` = published guides. `chat` = per tenant, under
  `tenant_scope`, every complete agent answer with its preceding user message (Gate 1 note c).
- `--limit N` caps sources per kind (for a cheap trial run).
