# Data model: Raw-store hardening

## raw_fetches (global, no RLS) — migration 0021

| Column | Change |
|---|---|
| `own_summary` | NEW `BOOLEAN NOT NULL DEFAULT false`. True when the row is the response to the app's own fixed summary query (`ReportSummary` single or `ReportsBatch`) with exact codes equal to `report_codes`. Written at insert/replace; backfilled by 0021 with the old lookup rule. |

Indexes:
- NEW `ix_raw_fetches_own_summary_codes`: GIN (`report_codes`) WHERE `own_summary`.
- DROPPED `ix_raw_fetches_summaries` (0020, `fetched_at DESC` WHERE operation name in summaries).

## raw_reports (global) — index only

- NEW `ix_raw_reports_public_checked`: (`checked_at`) WHERE `visibility = 'public'`.

## raw_fetch_grants (RLS tenant_isolation) — index only

- NEW `ix_raw_fetch_grants_tenant_granted`: (`tenant_id`, `granted_at`).

## In-process: tombstones (fetch_persistence)

- `_tombstones: _Tombstones` — `OrderedDict[str, datetime]` (code → seen at), ≤ `TOMBSTONE_MAX`
  (1024) entries, codes ≤ 32 chars, entries expire after `TOMBSTONE_TTL` (10 min).
- `_tombstones.floor: datetime | None` — the newest time of an entry evicted by overflow while
  younger than the TTL. A fetch naming a report with `requested_at <= floor` is stale.
- Bound: ≤ 1024 × ~250 B ≈ 256 KB + one timestamp.

## Write queue (FetchWriter)

- Capped items (`FetchedResponse`): ≤ `max_items`, ≤ `max_bytes` (unchanged).
- Uncapped items: `ReportGone` (client signals, salvaged summaries): codes + timestamp only.
