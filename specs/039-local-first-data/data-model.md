# Data model: Local-first data (039)

Migration `0018_raw_store_visibility` (down_revision `0017_proposal_user_rls`).

## raw_fetches (changed)

| Column | Change |
|---|---|
| `payload_hash` | **new** `String(64)` nullable: sha256 hex of the body without `_cost`. NULL for rows written before 0018 (first refetch rewrites them). |

`report_code` NULL when the single code is over 32 chars; `operation_name` truncated to 120.

## raw_reports (new, global, no RLS)

Per report: what WCL last showed us. Written by the fetch writer from summary bodies.

| Column | Type | Notes |
|---|---|---|
| `code` | `String(32)` PK | |
| `visibility` | `String(16)` NULL | `public` / `unlisted` (private → gone, never stored) |
| `end_time_ms` | `BigInteger` NULL | the report's `endTime` |
| `checked_at` | `timestamptz` NOT NULL | the fetch time of the body it came from; newer wins |

## raw_fetch_grants (new, tenant-scoped, RLS tenant_isolation)

| Column | Type | Notes |
|---|---|---|
| `tenant_id` | `uuid` FK tenants ON DELETE CASCADE | PK part |
| `report_code` | `String(32)` | PK part |
| `granted_at` | `timestamptz` NOT NULL | last successful WCL fetch of the code by this tenant |

## Rules

- **Visible(row, tenant, now)** ⇔ for every code in `row.report_codes`: len ≤ 32 and
  (`raw_reports.visibility = 'public'` and `checked_at ≥ now − reverify`) or (a grant for
  (tenant, code) with `granted_at ≥ now − reverify`). A row with no codes is visible to all
  (public WCL data, exact key only).
- **Fresh(row)**: research R6.
- **Gone(code)**: delete `raw_fetches` rows naming it and its `raw_reports` row; grants stay.
