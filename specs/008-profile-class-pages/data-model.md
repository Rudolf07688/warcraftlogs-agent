# Phase 1 Data Model: Profile & Class-Guide Pages

Scope: one new **global** table (`spec_guides`), the retirement of per-character guide
columns on `UserCharacter`, and the derived/transient structures for the Class Guides list
and the context preamble. Guide content is generic (non-user) data and is **not** tenant-scoped.

---

## 1. `SpecGuide` (NEW table `spec_guides`, GLOBAL) — US2 / FR-006, FR-007

One written guide per class+spec, shared across all users. Absence of a row ⇒ the spec is
"not downloaded".

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | `default uuid4` |
| `class_name` | String(40) | WCL PascalCase class filter value (e.g. `Paladin`) |
| `spec` | String(40) | WCL PascalCase spec filter value (e.g. `Protection`) |
| `guide_markdown` | Text \| null | populated when `status = ready` |
| `status` | String(10) | `pending` \| `ready` \| `failed` (a missing row = not-downloaded) |
| `created_at` | DateTime(tz) | `server_default=now()` |
| `updated_at` | DateTime(tz) | `server_default=now()`, `onupdate=now()` |

**Constraints / indexes**
- `UniqueConstraint(class_name, spec)` → `uq_spec_guide_identity` (dedup key; guards concurrent inserts).

**Validation / rules**
- `(class_name, spec)` MUST be a member of `CLASS_SPECS` (validated at the API boundary; unknown ⇒ 404).
- **No `tenant_id`, no RLS** — deliberate (plan Complexity Tracking). Runtime role granted DML by `0007` (consistent with `0004` default privileges).
- Lifecycle: `ensure_spec_guide` upserts `pending` then flips to `ready`/`failed`; `failed` is retryable (`force` or re-request). Dedup: `ready`/`pending` short-circuit unless `force`.

---

## 2. `UserCharacter` — EXTENDED/RETIRED COLUMNS — US3 / FR-016, FR-018

The character keeps its identity, relationship, raid role, and **resolved spec**; its guide
is now the shared `SpecGuide` for `(class_name, active_spec)`.

| Field | Change | Notes |
|-------|--------|-------|
| `class_name` | **kept** | resolved WCL class (keys into `spec_guides`; also feeds raid-role inference) |
| `active_spec` | **kept** | resolved WCL spec (keys into `spec_guides`) |
| `raid_role` | **kept** (feature 007) | unchanged |
| `guide_markdown` | **dropped (0008)** | content now lives in `spec_guides` |
| `guide_status` | **dropped (0008)** | derived from the matching `spec_guides` row |
| `guide_updated_at` | **dropped (0008)** | derived from the matching `spec_guides` row |

**Rules**
- Identity/uniqueness unchanged (`uq_user_char_identity`). Per-tenant + RLS unchanged.
- A character with no resolved spec has no guide (clean/unchanged behavior).
- `CharacterOut` continues to expose a `guide_status` (+ `guide_updated_at`) field, now **derived** from the character's spec guide (so the UI badge keeps working) — see contracts.

---

## 3. Derived / transient structures (not persisted)

### 3.1 Class Guides list item — US2 / FR-008

Per spec in the roster, merged with any `spec_guides` row:

```
{ class_name, class_display, spec, status: "ready"|"pending"|"failed"|"none", updated_at|null }
```

- Built from `CLASS_SPECS` (complete roster) left-joined to `spec_guides`; a spec with no row ⇒ `status = "none"`. Guarantees 100% coverage (SC-002).

### 3.2 Character guide status (derived) — US3 / FR-016

- `effective guide_status` for a character = the `status` of `spec_guides[(class_name, active_spec)]`, or `"none"` when the spec is unresolved or has no row.

### 3.3 Context preamble guide lookup — US3 / FR-016

- `ws._handle_turn` fetches `spec_guides` for the distinct `(class_name, active_spec)` of the tenant's profile characters and passes a `(class,spec) → markdown` map into `build_preamble`. Empty/unresolved ⇒ preamble byte-identical to today (consistent with feature 007 guarantees).

---

## Entity relationships

```text
spec_guides (NEW, GLOBAL)            # one guide per (class, spec); shared by everyone
   ▲ (looked up by class_name+spec)
   │
tenants (feature 006)
  └──< user_characters (per-tenant)  # keeps class_name/active_spec/raid_role; guide columns dropped
       (its guide = spec_guides[(class_name, active_spec)])
```

## Migrations (split for story independence)

Two migrations so US2 (the library) can ship without US3's read-path refactor, mirroring the
feature-007 split (`0005`/`0006`). Alembic history stays linear (`0006 → 0007 → 0008`).

### `0007_spec_guides` (US2; down_revision `0006_raid_role`)
1. `create_table("spec_guides", ...)` (global) with columns + `uq_spec_guide_identity`; grant the runtime role `SELECT, INSERT, UPDATE, DELETE` (mirror `0004`/prior migrations). No RLS.
2. **Backfill**: insert one `spec_guides` row per distinct `(class_name, active_spec)` from `user_characters` where `guide_status = 'ready'` and `guide_markdown` is not null, taking the most-recently-updated markdown per spec (dedup). No user-visible loss (FR-018).
3. **Keeps** the `user_characters` guide columns (the old per-character read-path still works until US3). Downgrade: `drop_table("spec_guides")`.

### `0008_drop_character_guide_columns` (US3; down_revision `0007_spec_guides`)
1. `drop_column("user_characters", "guide_markdown" | "guide_status" | "guide_updated_at")` — only after the read-path (`CharacterOut`, `profile_context`, `run_character_guide`) derives guides from `spec_guides`.
2. Downgrade: re-add the three columns (nullable). (Backfilled content is not restored to characters on downgrade — documented one-way data move.)

> Both need `import sqlalchemy as sa`; the `0007` backfill runs raw SQL as the migration owner. The `0008` column drop is sequenced after US3's refactor so the app never reads a dropped column.
