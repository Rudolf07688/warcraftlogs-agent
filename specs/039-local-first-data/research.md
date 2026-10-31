# Research: Local-first data (039)

## R1. What WCL can show us (threat model)

- **Decision**: treat every stored report as public or unlisted. The app uses OAuth client
  credentials, so WCL never returns a private report to it. "Private or deleted" shows up as
  `reportData.report: null` (with or without `errors`) on a later fetch.
- **Consequence**: the leak to prevent is (a) a tenant getting another tenant's unlisted data
  without having fetched that code from WCL, and (b) data staying served after its owner made
  the report private/deleted.

## R2. "A code the tenant already references" (clarify:039-references)

- **Decision**: a **grant** row (tenant, code, granted_at) written whenever a fetch made in a
  signed-in turn (`current_identity` set) succeeds from WCL for that code. WCL checked access
  at that moment, so a grant is WCL-verified.
- **Alternatives**: union over `tracked_raids`, `recent_raids`, `recent_mplus_runs`,
  `captured_graphs` and messages. Rejected: chat-pasted codes live only in free-text messages,
  four RLS tables to couple to, and every such code is fetched in a turn before it is analysed
  anyway (so it gets a grant).
- **Single-flight**: the flight task carries its first caller's context, so a joined caller from
  another tenant gets no grant (safe direction: its next read misses and grants itself).

## R3. "Public"

- **Decision**: `REPORT_SUMMARY_FIELDS` also selects `code visibility`; the writer reads
  `reportData.*` report objects in bodies containing `"visibility"` and upserts per-report
  status (visibility, endTime, checked_at). `"private"` is treated as gone.
- **Alternative**: extracting in SQL (JSON paths). Rejected: batch aliases (`r0…`) differ per
  query and SQLite/Postgres JSON functions differ.

## R4. Re-verify window (clarify:039-reverify)

- **Decision**: public status and grants count for `RAW_STORE_REVERIFY_DAYS` (7 at first, **1**
  after the bypass review, R9). After that the read misses, WCL is asked again and re-grants or
  reports the code gone.

## R5. Read hook placement

- **Decision**: `wcl_client.set_fetch_source(source)`; `AsyncWCLClient.query` awaits it **before**
  joining single-flight, in the caller's own context (identity), bounded by a timeout in the
  backend source. A hit returns the stored body through `_loads`; it is not offered to the sink
  and grants nothing.
- **Why here**: every WCL read passes `query`; Redis-cached families call it from their loaders,
  so the order Redis → store → WCL and the Redis back-fill come for free. Heavy uncached calls
  (tables, events, graphs) benefit most.
- **Rejected**: inside `_fetch` (the flight task) — a joined caller of another tenant would be
  served the first caller's visibility decision (bypass).

## R6. Freshness per family

| Family | Rule |
|---|---|
| Report data (row names ≥1 report) | Fresh when every report was **seen finished** (`is_finished(end, now=checked_at)`) and the row was fetched after it finished (`is_finished(end, now=fetched_at)`): kept and served indefinitely. Otherwise fresh only while younger than `WCL_CACHE_UNFINISHED_TTL` (120 s), the Redis rule for live reports. |
| Non-report data (rankings, characters, world/game data) | Never served from the store in this slice; the Redis family TTLs (char_overview 600 s, …) keep governing it. Visible to everyone by exact key (public WCL data, like Redis). |

## R7. Gone detection

- **Decision**: in `_fetch`, a query naming exactly one report whose response has
  `reportData.report` = null (parsed when `errors` exist, a byte regex otherwise) offers a
  `ReportGone(codes)` to the sink instead of the response. Batch queries are skipped; their
  callers fall back to per-code fetches. HTTP errors, rate limits, timeouts and validation
  errors (no `data`) are not "gone".
- The writer deletes `raw_fetches` rows whose `report_codes` contains the code, the code's
  `raw_reports` row, then evicts Redis `wcl:v1:report:<code>:*` (SCAN + DEL, glob-escaped).
  Grants stay (clarify:039-grant-rls).

## R8. Writer (sc-177)

- **Unchanged payload**: hash = sha256 of the body with the `_cost` object bytes removed. The
  writer SELECTs the stored hash; equal → `UPDATE fetched_at` only (no payload sent); different
  → full upsert. (clarify:039-unchanged-payload)
- **Batches**: the consumer takes up to 20 queued items and writes them in one transaction. On
  an error other than a timeout it retries each item alone; on a timeout (hung DB) the batch is
  counted failed. Never raises to callers.
- **Edge cases**: op name `[:120]`; `report_code` NULL when > 32 chars (clarify:039-overflow);
  the `\u0000` JSON escape removed escape-aware; `_Throttle.flush()` on stop; failure logs carry
  only exception class + SQLSTATE.
- **Retention**: none by age; the owner's rule (delete on gone). Monitoring query in
  quickstart.md and the architecture doc.

## R9. Redis relation

- Redis already serves report data by code to every tenant (keys hold no tenant). The store
  adds no wider *audience*: a store hit requires the stricter grant/public rule, and the only
  Redis change is evicting a gone report's keys.
- **Found in the bypass review**: a store hit back-fills the shared Redis entry, so a granted
  tenant's hit re-warms an entry other tenants (who know the code) read. Today a revoked report
  leaves Redis within its TTL (24 h) of the last WCL fetch; with the store, within the re-verify
  window plus that TTL. Hence the 1-day default (worst case ~48 h, vs ~24 h today), bounded and
  tunable. Closing it fully needs store hits that don't back-fill shared Redis, or tenant-aware
  Redis: backlog, not this slice (no Redis redesign).
