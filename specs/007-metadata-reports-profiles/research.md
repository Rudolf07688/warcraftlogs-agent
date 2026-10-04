# Phase 0 Research: Captured-Metadata Reuse, Findings-Based Reports & Role-Aware Profiles

All spec clarifications were resolved during `/speckit-specify` (recorded in spec Assumptions). This document records the **design decisions** that turn those requirements into an implementation shape, each grounded in the existing code. No `NEEDS CLARIFICATION` remain.

> **GitNexus (Principle VI)**: before editing, run impact analysis on the shared symbols this plan touches — `_handle_tool_end` (`backend/app/api/ws.py`), `build_preamble` (`backend/app/services/profile_context.py`), `render_report_pdf` + the two `reports.py` endpoints, `UserCharacter` (`backend/app/db/models.py`), and the `profile.py` routes. Each is on a hot path (every turn / every download / every profile write).

---

## Area 1 — Captured-metadata reuse (US1)

### Decision 1.1 — Reuse the existing capture hub and preamble; do not add a parallel path

- **Decision**: Add new best-effort capture calls inside `_handle_tool_end` (`ws.py:59-135`) alongside `capture_raid_from_tool` / `capture_graph_from_tool` / `capture_artifact_from_tool`, and include their writes in the existing commit-and-rescope guard (`ws.py:115-117`). Surface captured metadata by **extending `build_preamble`** (`profile_context.py:40-84`), the single injection path assembled at `ws.py:172-175` — not a second preamble.
- **Rationale**: Principle I (one authoritative implementation). The hub already defines the `capture_*_from_tool(session, *, tenant_id, name, ok, args, result, conversation_id)` contract and the best-effort/commit discipline; new captures mirror it exactly. The preamble already has the empty-state convention (`""` when nothing to add, `profile_context.py:46`) and char-budget caps.
- **Alternatives considered**: A new middleware/event bus (rejected: gratuitous infrastructure, Principle III); a second context block prepended separately (rejected: two sources of truth for agent context).

### Decision 1.2 — New per-tenant tables for known players and known encounters; derive known guilds

- **Decision**: Add `known_players` and `known_encounters` tables (per-tenant, mirroring `TrackedRaid`'s conventions: `tenant_id` FK with `ondelete=CASCADE`, a per-tenant `UniqueConstraint`, and a `(tenant_id, last_seen_at)` index). **Known raids** keep using `TrackedRaid` unchanged (FR-002). **Known guilds** are **derived** from the distinct non-null `TrackedRaid.guild` values (no new table).
- **Rationale**: `TrackedRaid` already captures raids/zones/guilds-per-report; a known-guild table would duplicate that (Principle I/III). Players (from character-ranking tools and report master-data actors) and standalone encounters (from `find_encounter`, which resolves a zone/boss with no report) are genuinely not captured today, so they need their own stores. Reusing `TrackedRaid`'s exact table conventions keeps access patterns uniform.
- **Alternatives considered**: One generic `known_entity(kind, payload_json)` table (rejected: untyped blob violates Principle IV and complicates dedup/query); extending `TrackedRaid.encounters` to also hold standalone `find_encounter` results (rejected: conflates report-scoped bosses with account-wide known encounters).

### Decision 1.3 — Capture sources and dedup keys

- **Known players** come from successful `get_character_zone_rankings` / `get_character_encounter_rankings` (name/server/region/class/spec in args+result) and `get_report_master_data` actors. Dedup key: `(tenant_id, lower(name), server, region)`; `class_name`/`spec` filled when available, `last_seen_at` touched on re-sighting. A player already present in the profile (`UserCharacter`) is still recorded but de-duplicated against the profile when building the preamble so it is not listed twice (edge case in spec).
- **Known encounters** come from successful `find_encounter` matches (encounter id + name + zone id/name). Dedup key: `(tenant_id, encounter_id)`.
- **Rationale**: These tool outputs already contain the data (no new WCL queries — Principle I/III and FR notes). Extractors are pure functions mirroring `encounters_from_tool` (`services/encounters.py`).

### Decision 1.4 — Bounded, recency-selected injection

- **Decision**: In `build_preamble`, append a `RECENTLY SEEN (this account)` section listing the top-N most recent known raids (by `last_asked_at`), known players, and known encounters (by `last_seen_at`), plus derived known guilds, under new character/count caps (reusing the `_trim` helper and the spirit of `_TOTAL_GUIDE_CHARS`). `ws.py` fetches the capped lists and passes them to `build_preamble`.
- **Rationale**: FR-007 (bounded context), SC-003 (fixed budget regardless of history). Recency ordering uses the indexes already defined (`ix_tracked_raids_tenant_asked`) and mirrored on the new tables.
- **Numbers (initial)**: ≤ 10 raids, ≤ 15 players, ≤ 10 encounters, whole block trimmed to a fixed char cap (e.g. 2000). Tunable; documented as constants next to the existing caps.

---

## Area 2 — Findings-based reports (US2/US3)

### Decision 2.1 — One synthesis step feeding the unchanged renderer

- **Decision**: Add `services/report_synthesis.py` with `async synthesize_findings(messages: list[dict], *, scope: str, question: str | None) -> str` returning findings **markdown**. Both `reports.py` endpoints build their existing message slice, call `synthesize_findings`, and pass the result to `render_report_pdf` as a **single synthetic agent message** (`[{"role": "agent", "content": findings_md, "status": "complete"}]`) plus the existing graphs/artifacts. `render_report_pdf` is unchanged.
- **Rationale**: Principle I — the renderer already turns agent markdown (headings/tables/lists/math) into the PDF body and attaches charts (`pdf_report.py:179-385`); feeding it synthesized markdown instead of the transcript needs **zero renderer changes**. One helper `_synthesize_and_render(...)` placed in `reports.py` keeps both scopes on one pipeline (FR-016).
- **Alternatives considered**: A new `body_markdown` parameter on `render_report_pdf` (rejected: the synthetic-message approach reuses the existing signature with no edit); rendering synthesis + original transcript (rejected: the whole point is *findings, not what was said*, FR-012).

### Decision 2.2 — LLM call pattern: one-shot `google-genai`, off-loop, bounded

- **Decision**: Use the `suggestions.generate_followups` pattern (`suggestions.py:82-103`): `genai.Client().models.generate_content` via `asyncio.to_thread`, non-web-search, with the whole in-scope chat as input. Wrap in `asyncio.wait_for(...)` with a bounded timeout. Model from a new setting `wcl_report_model` (default `gemini-3.6-flash`, matching `wcl_guide_model`/`_SUGGEST_MODEL`).
- **Rationale**: Findings come from the chat itself, so no web search is needed (spec Assumption); the one-shot pattern is the cheapest precedent and already proven off-loop and fail-safe. Distinct from `guide._generate_text` (`guide.py:89-98`), which spins a full ADK session for web-grounded generation — unnecessary here.
- **Alternatives considered**: Reuse `_generate_text` (rejected: heavier, web-search-capable session not needed); stream via the user's selected chat model (rejected: synthesis must be independent of chat-model choice and cheap).

### Decision 2.3 — Failure, empty-findings, and long-input handling

- **Decision**:
  - **Failure/timeout/empty model output** → raise, caught by the existing fail-closed `_render` wrapper (`reports.py:81-93`) returning `500 pdf_generation_failed`; never a partial file (FR-018).
  - **No substantive findings** (chit-chat) → the prompt instructs the model to emit a short "No substantive findings were recorded." document; both scopes still render attached charts (FR-017).
  - **Very long conversations** → cap the characters fed to the model (truncate oldest first, keep a budget), documented in the synthesis module (edge case / FR degrade-gracefully).
- **Rationale**: Reuses the endpoint's existing error contract; keeps synthesis bounded and honest.

### Decision 2.4 — No caching (per-download synthesis)

- **Decision**: Synthesize on every download; do not persist synthesized reports.
- **Rationale**: Confirmed with the user and recorded in spec Assumptions; simplest (Principle III). A cache + invalidation layer can be added later behind the same `synthesize_findings` interface if cost/latency warrant.

---

## Area 3 — Role-aware profile: multiple friends + raid roles (US4)

### Decision 3.1 — Multiple friends: verify + polish only

- **Decision**: No backend change for multi-friend (already supported: `add_friend` inserts per call with no cap; `profile.py:57-76` only rejects exact duplicates with 409 `duplicate_friend`). Frontend change: map the 409 to a friendly "already added" message in `ProfilePanel.tsx` (currently a generic failure).
- **Rationale**: FR-022/FR-023; the capability exists (confirmed in code) — Principle I says don't rebuild it.

### Decision 3.2 — `raid_role` as a nullable override column; effective role computed

- **Decision**: Add `UserCharacter.raid_role` (nullable `String`, values `"tank" | "healer" | "dps" | NULL`) as the **user override**. The **effective role** = `raid_role` if set, else `role_for_spec(active_spec)` (inferred), else unset. This is computed at the read/preamble boundary, not stored, so a later spec re-resolution updates the inferred default while the override persists (FR-025/FR-026).
- **Rationale**: FR-024..FR-026, FR-031. A nullable additive column needs no backfill; existing rows read back as `NULL` (unset override) and simply show their inferred-or-unset role. The existing `role` column (`"self"|"friend"`) is untouched — the naming collision is avoided by a distinct column name (`raid_role`).
- **Alternatives considered**: Store the effective role (rejected: would need rewrites whenever spec re-resolves and loses the override-vs-inferred distinction, FR-029); overload the existing `role` column (rejected: conflates orthogonal concepts, Principle IV).

### Decision 3.3 — `SPEC_ROLES` single source of truth for spec→role

- **Decision**: Add `SPEC_ROLES: dict[str, str]` and `role_for_spec(spec: str | None) -> str | None` to `wcl_agent/constants.py`, keyed by the same PascalCase spec filter values already in `CLASS_SPECS`. Spec names map unambiguously to a role across classes (verified): tanks = `Blood, Vengeance, Guardian, Brewmaster, Protection`; healers = `Restoration, Preservation, Mistweaver, Holy, Discipline`; everything else = `dps`. Unknown/ambiguous/None → `None` (unset, not guessed — edge case).
- **Rationale**: Principle I — `constants.py` is already the SSOT for class/spec reference data; role mapping belongs there. Verified no spec name maps to two different roles (e.g. `Holy` is healer for both Paladin and Priest; `Protection` is tank for both Paladin and Warrior; `Frost`/`Restoration` are consistent within their role), so a spec-name→role dict is sufficient without class disambiguation.
- **Alternatives considered**: `(class, spec)`-keyed map (rejected: unnecessary given verified uniqueness; simpler dict preferred); inferring from WCL metric (rejected: metrics are DPS/HPS query params, not raid roles).

### Decision 3.4 — Edit path for friend roles

- **Decision**: Add `PATCH /api/profile/friends/{char_id}` accepting `{raid_role}` to edit a friend's role in place (self already uses upsert on `PUT /self`). Setting `raid_role` to null clears the override (returns to inferred). Preserve `commit_and_rescope` + `schedule_character_guide` conventions.
- **Rationale**: FR-026/FR-028 require in-place edits; re-posting via `add_friend` would hit the identity unique constraint. `PATCH` is the minimal additive endpoint.
- **Alternatives considered**: Delete+re-add (rejected: loses `id`/guide, churns the row); a general friend PUT (rejected: identity edits are out of scope — only the role changes).

### Decision 3.5 — Preamble shows effective role

- **Decision**: Extend `_ident` (`profile_context.py:27-30`) to append the effective role in the existing `" — "` style (e.g. `Thrall-Area52 (US) — Warrior — Protection — Tank`); when unset, the line is byte-identical to today (FR-030).
- **Rationale**: Reuses the existing identity formatter and degrade-gracefully convention (unset spec already omits cleanly).

---

## Cross-cutting decisions

- **Migration (split for independence)**: two Alembic revisions — `0005_known_entities` (down_revision `0004_rls`) creating `known_players` + `known_encounters`, and `0006_raid_role` (down_revision `0005_known_entities`) adding `user_characters.raid_role` (nullable). The split keeps US1 (tables) and US4 (column) independently deliverable; new tables get the same RLS policy treatment as peers (feature 006) — see data-model.md.
- **Tenant isolation**: every new table carries `tenant_id`; all reads go through the tenant-scoped session; captures occur inside the already-scoped turn transaction. No cross-tenant exposure (FR-006, SC-001).
- **Config**: add `wcl_report_model` to `Settings` (`config.py`), default `gemini-3.6-flash`.
- **Testing**: pytest units for `role_for_spec`, the player/encounter extractors (pure functions), `build_preamble` with/without captured metadata and roles (empty-state byte-equality), `synthesize_findings` (mock the genai client) incl. empty/failure paths, and the new PATCH endpoint + duplicate-friend message.
