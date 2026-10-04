# Phase 1 Data Model: Captured-Metadata Reuse, Findings-Based Reports & Role-Aware Profiles

Scope: two new per-tenant tables, one new column, and the derived/transient structures used for context injection and report synthesis. All persistent entities carry `tenant_id` and follow the feature-006 RLS pattern. Schema is split across **two** migrations so US1 and US4 remain independently deliverable: `0005_known_entities` (US1 tables, down_revision `0004_rls`) and `0006_raid_role` (US4 column, down_revision `0005_known_entities`).

---

## 1. `KnownPlayer` (NEW table `known_players`) — US1 / FR-003

A WoW character the user has encountered via **tool results** (character rankings, report actors), distinct from profile characters.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | `default uuid4` |
| `tenant_id` | UUID FK → `tenants.id` | `ondelete=CASCADE`, not null |
| `name` | String(100) | required |
| `server` | String(100) | required |
| `region` | String(8) | required |
| `class_name` | String(40) \| null | filled when the source result includes it |
| `spec` | String(40) \| null | filled when available |
| `source` | String(20) \| null | `"ranking"` \| `"master_data"` (provenance; optional) |
| `first_seen_at` | DateTime(tz) | `server_default=now()` |
| `last_seen_at` | DateTime(tz) | touched on re-sighting (recency) |

**Constraints / indexes**
- `UniqueConstraint(tenant_id, name, server, region)` → `uq_known_player_identity`
- `Index(tenant_id, last_seen_at)` → `ix_known_players_tenant_seen`

**Validation / rules**
- Captured only on a **successful** tool call (`ok` true). Missing server/region ⇒ the record is skipped (identity must be unambiguous — edge case).
- Dedup upsert: existing identity ⇒ touch `last_seen_at` and backfill null `class_name`/`spec` if newly known.
- Best-effort: a write failure is swallowed and never blocks the turn (FR-008).

---

## 2. `KnownEncounter` (NEW table `known_encounters`) — US1 / FR-004

A raid zone/boss the user has queried or resolved (primarily via `find_encounter`), independent of any report.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | `default uuid4` |
| `tenant_id` | UUID FK → `tenants.id` | `ondelete=CASCADE`, not null |
| `encounter_id` | Integer | the WCL encounter id (dedup key) |
| `encounter_name` | String(120) | required |
| `zone_id` | Integer \| null | when known |
| `zone_name` | String(120) \| null | when known |
| `first_seen_at` | DateTime(tz) | `server_default=now()` |
| `last_seen_at` | DateTime(tz) | touched on re-sighting |

**Constraints / indexes**
- `UniqueConstraint(tenant_id, encounter_id)` → `uq_known_encounter_identity`
- `Index(tenant_id, last_seen_at)` → `ix_known_encounters_tenant_seen`

**Validation / rules**
- Captured only when `find_encounter` (or an equivalent) returns a match with a numeric `encounter_id`. Name-only matches without an id are skipped (keeps dedup simple — Principle III).
- Dedup upsert by `(tenant_id, encounter_id)`; touch `last_seen_at`, backfill null zone fields when newly known.

---

## 3. `UserCharacter` — EXTENDED — US4 / FR-024..FR-026, FR-031

Add one nullable column; the existing `role` (`"self"|"friend"`) column is **unchanged**.

| New field | Type | Notes |
|-----------|------|-------|
| `raid_role` | String(10) \| null | the **user override**: `"tank"` \| `"healer"` \| `"dps"` \| `NULL` (unset) |

**Rules**
- `raid_role` is the explicit override. The **effective role** is computed, not stored:
  `effective_role = raid_role or role_for_spec(active_spec)` → one of `tank|healer|dps|None`.
- Nullable, no backfill: rows created before `0006_raid_role` read back `raid_role = NULL` and show their inferred-or-unset role (FR-031).
- Identity/uniqueness rules unchanged (`uq_user_char_identity` on `tenant_id,name,server,region,role`); a role change is an in-place edit, never a new row (FR-028).
- Allowed override values validated at the API boundary (Pydantic `Literal`); any other value ⇒ 422, character unchanged (FR-027).

---

## 4. `TrackedRaid` — UNCHANGED (reused) — US1 / FR-002

Existing table continues to capture known raids. **Known guilds** (spec entity) are **derived** at read time as the distinct non-null `TrackedRaid.guild` values per tenant (most-recent first) — no new table.

---

## 5. Derived / transient structures (not persisted)

### 5.1 Captured-metadata context section — US1 / FR-005, FR-007

Assembled per turn in `ws.py` and passed into `build_preamble`; appended as a bounded `RECENTLY SEEN (this account)` block.

- Inputs (capped, recency-ordered):
  - known raids: top ≤10 `TrackedRaid` by `last_asked_at`
  - known players: top ≤15 `KnownPlayer` by `last_seen_at`, **minus** any already in the profile (dedup vs `UserCharacter`)
  - known encounters: top ≤10 `KnownEncounter` by `last_seen_at`
  - known guilds: distinct `TrackedRaid.guild` (derived)
- Whole block trimmed to a fixed character cap (reuses `_trim`); empty inputs ⇒ no block, preamble byte-identical to today (FR-011, SC-003).

### 5.2 Effective raid role — US4 / FR-030

- `role_for_spec(spec)` from `wcl_agent/constants.SPEC_ROLES` (SSOT). `_ident` appends the effective role in the existing `" — "` style; unset ⇒ omitted cleanly.

### 5.3 `FindingsReport` (synthesis output) — US2/US3 / FR-012, FR-013

- Transient markdown produced by `synthesize_findings(messages, scope, question)`; not persisted (Decision 2.4).
- Suggested section shape the prompt targets (where content supports it): **Summary / Investigated**, **Key Findings** (metrics), **Per-boss / Per-player results**, **Recommendations**. Empty-findings ⇒ a short "no substantive findings" document.
- Rendered as the PDF body via the existing `render_report_pdf` (fed as a single synthetic agent message); charts/graphs attached exactly as today, scoped per endpoint.

---

## Entity relationships

```text
tenants (feature 006)
  ├──< tracked_raids        (existing; known raids + derived known guilds)
  ├──< known_players        (NEW)
  ├──< known_encounters     (NEW)
  ├──< user_characters      (EXTENDED: + raid_role)  — self/friend
  ├──< guild_profile        (existing; single main guild)
  ├──< conversations ──< messages / captured_graphs / artifacts (existing; report inputs)
  └── (all new tables mirror the per-tenant RLS policy applied in 0004_rls)
```

## Migrations (split for story independence)

### `0005_known_entities` (US1; down_revision `0004_rls`)
1. `create_table("known_players", ...)` with the columns, unique constraint, and index above.
2. `create_table("known_encounters", ...)` likewise.
3. Apply the same RLS enable + tenant policy to both new tables as `0004_rls` applies to peer per-tenant tables (USING/WITH CHECK on `tenant_id = current_setting('app.tenant_id')`).
4. Downgrade drops the two tables (reverse order).

### `0006_raid_role` (US4; down_revision `0005_known_entities`)
1. `add_column("user_characters", Column("raid_role", String(10), nullable=True))` — no backfill.
2. Downgrade drops the column.

> Both migrations need `import sqlalchemy as sa` and the project's UUID/JSON helpers (see the 0004 fix history); grant the runtime role privileges on the new tables consistent with prior migrations. Alembic history is linear, so `0006` follows `0005` in apply order — this is sequencing only, not a behavioral coupling (US1 ships without `raid_role`).
