# Phase 0 Research: Profile & Class-Guide Pages

Design decisions for the dedicated profile page, the shared spec-guide library, and the
reconciliation/migration of existing per-character guides. No open NEEDS CLARIFICATION
remain (the two scope decisions were confirmed with the user; see spec checklist notes).

---

## Decision 1 — Guide storage: one global `spec_guides` table keyed by (class, spec)

**Decision**: Store guides in a single global table `spec_guides(class_name, spec, guide_markdown, status, created_at, updated_at)` with a unique constraint on `(class_name, spec)`. No `tenant_id`, no RLS. Presence + `status` drives the Class Guides list (absent row = "not downloaded").

**Rationale**: The user chose a spec-keyed library shared across all users. Guides are generic, non-user content, so a global store is correct and removes per-user/per-character duplication of identical content (Principle I). It is also *simpler* than a tenant-scoped + RLS table (Principle III).

**Alternatives considered**:
- *Per-character guide columns (today)* — duplicates identical content per character, no sharing, no retry. Rejected (the defect we're fixing).
- *Per-tenant `spec_guides`* — still duplicates identical guides per user and re-spends model budget; RLS protects content that isn't sensitive. Rejected.

**Isolation note**: This is the one deliberate deviation from feature-006's all-tenant-scoped convention (tracked in plan Complexity Tracking). The table holds no user data; endpoints still require auth, mutations require CSRF + rate limit.

---

## Decision 2 — Guide lifecycle, dedup, and retry

**Decision**: A single `ensure_spec_guide(class_name, spec, *, force=False)` drives the lifecycle:
- row `ready` and not `force` → no-op (dedup; SC-004).
- row `pending` → no-op (generation already in flight; FR-013).
- row absent / `failed` / (`force`) → upsert `status="pending"`, spawn the existing off-loop generation; on success → `ready` + markdown; on error/empty → `failed`.

Concurrency is guarded by (a) the in-process in-flight set already in `guide.py` (re-keyed to `(class, spec)`) and (b) the DB unique constraint on `(class, spec)` (a losing concurrent insert catches `IntegrityError` and reads the winner). Retry/refresh is just `ensure_spec_guide(..., force=True)` (or a call when `failed`).

**Rationale**: Reuses the proven best-effort generation pattern; makes `failed` a transient, retryable state (fixes the stuck-guide defect, FR-010/FR-011). Single function = one authoritative path (Principle I).

**Alternatives considered**: A per-character retry button only — rejected; doesn't give the browse-all-specs/manual-add capability the user asked for, and keeps duplication.

---

## Decision 3 — Rate limiting manual generation

**Decision**: Reuse `auth/rate_limit.InProcessRateLimiter` with a dedicated instance (`guide_limiter`) and a new setting `wcl_guide_generate_per_minute` (default e.g. 10). The generate endpoint keys the limiter by `user_id` (from the session); over-limit → `429 {"code":"rate_limited"}` with `Retry-After`.

**Rationale**: The earlier guide failures were plausibly a Warcraft Logs / model rate-limit cascade. Bounding user-initiated generation protects upstream budgets (FR-014) and reuses the existing limiter (Principle I). In-process is sufficient at this scale (single process).

**Alternatives considered**: No limit (rejected — invites the cascade we're fixing); distributed limiter (rejected — YAGNI at this scale).

---

## Decision 4 — Character guide read-path & preamble (reuse by spec)

**Decision**: `UserCharacter` keeps its resolved `class_name`/`active_spec` (per-character, from WCL) but no longer stores guide content. A character's guide is the `spec_guides` row for its `(class_name, active_spec)`. The feature-007 `build_preamble` is extended to receive a `(class,spec) → markdown` lookup; `ws._handle_turn` fetches the relevant `spec_guides` rows for the tenant's profile characters and passes them in. `CharacterOut` exposes a derived `guide_status` (and keeps `guide_updated_at`) sourced from the matching spec guide.

**Rationale**: One source of truth for guide content (Principle I); the preamble behavior is otherwise unchanged (empty/unresolved ⇒ byte-identical, consistent with 007). The preamble reader stays tenant-agnostic for guides because guide content is global.

**Alternatives considered**: Keep per-character guide columns as a cache mirror of the spec guide — rejected (two sources of truth; drift).

---

## Decision 5 — Character generation flow → spec guide

**Decision**: `run_character_guide` is refactored to: resolve `(class, spec)` from WCL (as today, per character), persist `class_name`/`active_spec` on the character, then call `ensure_spec_guide(class, spec)`. It no longer writes per-character markdown. Auto-fetch on add (US3) therefore reuses an existing ready guide (zero regeneration) or triggers one into the shared library.

**Rationale**: Keeps the valued "auto-fetch on add" UX (FR-015) while feeding the single store; reuses `resolve_active_spec` unchanged.

**Alternatives considered**: Drop auto-fetch entirely (rejected — user explicitly wants it kept).

---

## Decision 6 — Migration of existing per-character guides

**Decision**: **Two** migrations (split for story independence, like feature-007's `0005`/`0006`):
- `0007_spec_guides` (US2): `create_table("spec_guides", ...)` (global, unique `(class_name, spec)`, runtime-role DML grant); **backfill** one row per distinct `(class_name, active_spec)` among existing `user_characters` with a `ready` guide (most-recent markdown per spec; dedup; FR-018). **Keeps** the per-character guide columns so the old read-path still works until US3.
- `0008_drop_character_guide_columns` (US3): drop `user_characters.guide_markdown/guide_status/guide_updated_at` (keep `class_name`, `active_spec`) — only after the read-path derives guides from `spec_guides`. Downgrade re-adds the columns.

**Rationale**: Lets US2 (the library) ship without US3's read-path refactor (each story independently deliverable, Principle II) while still ending single-source once US3 lands. Avoids ever reading a dropped column.

**Alternatives considered**: One migration that creates+backfills+drops — rejected because it forces US2 and US3 to land together (couples the stories, which `/speckit-analyze` would flag). Keeping the columns permanently unused — rejected (dead columns, drift, Principle I/III).

**Note**: Linear history `0006 → 0007 → 0008`; both need `import sqlalchemy as sa`; the `0007` backfill reads `user_characters` directly via SQL as the migration owner.

---

## Decision 7 — Guides API surface (global, authenticated)

**Decision**: New `api/guides.py` router using the **non-tenant** DB dependency (`db/session.get_session`, since `spec_guides` isn't RLS-scoped) but still `require_session` (and `require_csrf` for mutations):
- `GET /api/guides` → full roster (from `CLASS_SPECS`) merged with statuses → `GuideListOut`.
- `GET /api/guides/{class_name}/{spec}` → `GuideOut` (status + markdown when ready; 404 if class/spec not in the roster).
- `POST /api/guides/{class_name}/{spec}/generate` → kick off `ensure_spec_guide` (body `{force?: bool}`); rate-limited; returns current `GuideOut` (status `pending`).

**Rationale**: Clean REST surface mirroring existing routers; typed Pydantic I/O (Principle IV); async (Principle V). Roster from the SSOT so the list is always complete (SC-002).

**Alternatives considered**: Fold into `profile.py` — rejected; guides are global, not tenant-profile data, so a separate router is clearer and avoids the tenant-DB dependency.

---

## Decision 8 — Frontend: routed page + tabs + theme

**Decision**: Add a guarded top-level route `/profile` (mirroring `/admin/users`) rendering `ProfilePage.tsx`, which hosts two tabs: **Characters** (extracted from `ProfilePanel`) and **Class Guides** (new). Replace the modal open in `App.tsx` with navigation to `/profile`; retire `ProfilePanel`. Warcraft theming via CSS tokens + component classes in `styles.css`/`index.css`. Guide content renders via the existing `StreamMarkdown`.

**Rationale**: Mirrors the existing routing pattern; tabs keep both concerns in one page; reusing `StreamMarkdown` avoids a second markdown renderer (Principle I).

**Alternatives considered**: Nested routes under `/app/*` — workable but the chat `App` shell owns that space; a sibling guarded route is cleaner and matches `/admin/users`.

---

## Decision 9 — Guide-fetch failure root cause (the defect)

**Decision**: Treat the "old friends' guides stuck unavailable" as the `failed`-is-terminal design flaw plus likely transient WCL/model rate limits. This feature's retry (Decision 2) + rate limiting (Decision 3) resolve it structurally. A separate quick diagnosis of the live failure (rate limit vs. Vertex ADC in the container) can run alongside, but no extra mechanism is needed beyond retry + bounded generation.

**Rationale**: The feature's requirements already make failures recoverable; no speculative work (Principle III).

---

## Cross-cutting

- **GitNexus (Principle VI)**: run impact analysis before editing `build_preamble`, `run_character_guide`/`schedule_character_guide`, `UserCharacter`, `profile.py`, and `ws._handle_turn` (tasks T001).
- **Reuse ledger**: `CLASS_SPECS` (roster), `_generate_text`/`_GUIDE_PROMPT` (generation), `resolve_active_spec` (spec resolution), `InProcessRateLimiter` (throttle), `StreamMarkdown` (render), `get_session`/`require_session`/`require_csrf` (auth/DB), the `000N_*` migration pattern.
