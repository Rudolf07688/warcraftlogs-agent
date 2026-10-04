# Feature Specification: Profile & Class-Guide Pages — Dedicated, Themed, with a Shared Spec-Guide Library

**Feature Branch**: `008-profile-class-pages`

**Created**: 2026-10-04

**Status**: Draft

**Input**: User description: "Promote and upgrade the profile and class pages. Revamp the profile modal — promote it to its own page, make the buttons and things look good (very basic at the moment), keep it thematic to Warcraft. Add a retry to fetch the class guides. Make the class guides a tab of its own. List all classes/specs and let the user manually add (fetch) them at will (keep the auto-fetching on add), clearly showing which specs' guides are already downloaded."

## Context

Today the profile lives in a **modal** (`ProfilePanel`) opened from the chat view: it manages the user's own character, multiple friends (each with a raid role — feature 007), and one main guild. It is functional but visually basic. **Spec guides** are generated per character: when a character is saved, a background task resolves its Warcraft-Logs spec and generates a written guide stored *on that character*, with a status of `pending → ready | failed`. There is **no retry** — a guide that fails (e.g. a transient Warcraft Logs rate limit, a model/credentials error) is stuck `failed` forever, and the same spec is re-generated independently for every character that happens to share it.

This feature does three things:

1. **Promotes the profile from a modal to a dedicated, Warcraft-themed page** with a tabbed layout and polished controls.
2. **Introduces a shared, spec-keyed guide library** (one guide per class+spec, reused by every character of that spec and shared across all users) with its own **Class Guides tab** that lists every class and spec, shows which guides are already downloaded, lets the user manually request any guide, and **retries** failed/missing ones.
3. **Keeps the existing behaviour** that saving a character auto-triggers its spec's guide — now feeding the shared library (deduplicated) rather than a per-character copy.

Guide content is **generic class/spec advice, not user data**, so the library is global; all genuinely user-owned data (characters, friends, guild, raid roles, conversations) remains strictly per-tenant as established in feature 006.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dedicated, themed Profile page (Priority: P1)

As a signed-in user, I open my profile as its own full page (not a cramped modal) with a clear, Warcraft-themed layout and well-styled controls, organized into tabs. Everything I could do before — set my own character, add and remove multiple friends, set each character's raid role (Tank/Healer/DPS, inferred or overridden), and set my main guild — is available here, but easier to read and use.

**Why this priority**: The page is the container for everything else in this feature and is the user's headline ask ("promote it to its own page… make the buttons and things look good"). It delivers immediate value on its own and every other story lives inside it.

**Independent Test**: Navigate to the profile page from the main app in one step; confirm it presents the current profile (self, friends with roles, guild) and supports all existing create/update/remove actions with a coherent themed design, without the old modal.

**Acceptance Scenarios**:

1. **Given** I am signed in, **When** I open my profile, **Then** it appears as a dedicated page reachable from the main navigation (not a modal overlay), and the chat view is no longer where profile editing happens.
2. **Given** the profile page is open, **When** I view it, **Then** profile management is organized into tabs (at least a Characters/Profile tab and a Class Guides tab) and I can switch between them without losing my place.
3. **Given** I am on the Characters tab, **When** I add my own character, add several friends, change a friend's raid role, clear a role back to inferred, and set a main guild, **Then** each action works and persists exactly as before, with clearer controls and status indicators.
4. **Given** I try to add a friend I already have (same name/server/region), **When** I submit, **Then** I see a friendly "already added" message, not a generic error.
5. **Given** the page on a typical desktop screen, **When** I view and interact with it, **Then** the layout, buttons, inputs, and selects follow a consistent Warcraft-themed visual style and remain legible and usable.

---

### User Story 2 - Class Guides tab with a shared spec-guide library (Priority: P1)

As a user, I open a **Class Guides** tab that lists every class and each of its specs. For each spec I can see at a glance whether its guide is already **downloaded**, and I can **manually request** a guide for any spec I like — even one I have no character for. If a guide failed or was never generated, I can **retry**. Once generated, the guide is available to me and to everyone, and to any character of that spec, without being generated again.

**Why this priority**: This is the core new capability and directly fixes the "guides get stuck and never retry" pain. It is independently valuable: a user can build out the guide library regardless of their character roster.

**Independent Test**: Open the Class Guides tab; confirm all classes/specs are listed with an unambiguous per-spec status; request a guide for a spec with no character; confirm it transitions to downloaded and its content is viewable; force a failure and confirm it can be retried rather than being stuck.

**Acceptance Scenarios**:

1. **Given** the Class Guides tab, **When** it loads, **Then** every class and all of its specs are listed, each showing a clear status: downloaded, generating, failed, or not downloaded.
2. **Given** a spec with no guide yet, **When** I request its guide, **Then** generation starts (shown as "generating") and, on success, the spec shows as downloaded with its content viewable.
3. **Given** a spec whose guide generation failed, **When** I retry it, **Then** a fresh attempt runs and the status updates accordingly; a failed guide is never permanently stuck.
4. **Given** a spec whose guide is already downloaded, **When** another character of that same spec exists or is added, **Then** that character reuses the existing guide and no duplicate generation occurs.
5. **Given** a downloaded guide, **When** I choose to refresh/regenerate it, **Then** a new version is generated and replaces the old one on success.
6. **Given** I rapidly request many guides, **When** the requests exceed a safe rate, **Then** the system bounds generation (so upstream data/model budgets are protected) and tells me rather than failing silently or cascading errors.
7. **Given** a guide was generated by anyone, **When** I view that spec, **Then** I see the downloaded guide (the library is shared across users).

---

### User Story 3 - Auto-fetch on add, reconciled with the shared library (Priority: P2)

As a user, when I save my own character or add a friend, the system still automatically ensures that character's spec guide exists — but it now contributes to the shared library and reuses an existing guide instead of regenerating one. My characters show their spec's guide, and the assistant uses it as standing context, exactly as before.

**Why this priority**: It preserves the convenient "it just fetches when I add someone" behaviour while removing duplication. It builds on US2's library, so it ships after it.

**Independent Test**: Add a friend whose spec already has a ready guide and confirm it attaches instantly with no new generation; add a friend of a spec with no guide and confirm generation is triggered into the shared library; confirm the character's guide appears in the profile and in the assistant's context.

**Acceptance Scenarios**:

1. **Given** a spec guide that is already downloaded, **When** I add a character of that spec, **Then** the character immediately reflects the existing guide and no new generation is triggered.
2. **Given** a spec with no guide, **When** I add a character of that spec, **Then** guide generation is triggered automatically into the shared library (best-effort, non-blocking).
3. **Given** a character whose spec cannot be resolved, **When** it is saved, **Then** no guide is attached and the character remains fully usable (consistent with today).
4. **Given** a character with a resolved spec that has a ready guide, **When** the assistant answers a question about that character, **Then** the guide is available as standing context as it is today.
5. **Given** I remove a character, **When** the removal completes, **Then** the shared spec guide is not deleted (other characters/users may rely on it).

---

### Edge Cases

- **Concurrent requests for the same spec** (two users, or one user adding two same-spec characters at once) resolve to a **single** generation; both see the result (deduplicated by class+spec).
- A spec that maps to no clear role is still listed and its guide can be requested directly by spec.
- **Guide generation failure** (upstream rate limit, model error, missing credentials) ends in a `failed` status that is **retryable**, with a clear message; it never blocks the page or gets permanently stuck (this is the defect motivating the feature).
- **Rate-limited manual requests**: a user cannot hammer generation; excess requests are throttled with clear feedback rather than cascading failures.
- Guides that were stuck `failed` before this feature become retryable afterward.
- Very long guide content is presented readably (scroll/sections), and an empty/placeholder guide is distinguished from a real one.
- Navigating away from the page while a guide is generating does not cancel it; the status is correct on return.
- The shared, global guide library must never expose or mix in any per-tenant user data; only generic class/spec guide content is global.

## Requirements *(mandatory)*

### Functional Requirements

**Profile page (US1)**

- **FR-001**: The profile MUST be presented as a dedicated, routable page reachable from the main application navigation, replacing the current modal as the place to manage the profile.
- **FR-002**: The profile page MUST use a tabbed layout with at least a Characters/Profile tab and a Class Guides tab, and switching tabs MUST NOT lose unsaved context in the other tab.
- **FR-003**: The page MUST preserve all existing profile capabilities: set the single self character; add and remove an unlimited number of friends; set/override/clear each character's raid role (with the inferred-from-spec default); and set/replace/remove the single main guild.
- **FR-004**: A duplicate friend (same name/server/region) MUST be rejected with a clear "already added" message.
- **FR-005**: The page MUST present a consistent Warcraft-themed visual style across its controls (buttons, inputs, selects, cards, status indicators), legible and usable on a typical desktop screen.

**Shared spec-guide library & Class Guides tab (US2)**

- **FR-006**: The system MUST maintain guides keyed by **class + spec** (one guide per spec), reused by every character of that spec rather than duplicated per character.
- **FR-007**: The guide library MUST be **shared across all users** (global): a guide generated by anyone is visible to everyone; no per-tenant user data may appear in it.
- **FR-008**: The Class Guides tab MUST list **every** class and all of its specs, each with an unambiguous status: downloaded (ready), generating (pending), failed, or not downloaded.
- **FR-009**: Users MUST be able to **manually request** a guide for any spec at will, including specs for which they have no character.
- **FR-010**: Users MUST be able to **retry** a failed or not-downloaded guide, and to **refresh/regenerate** an existing one; a guide MUST never be permanently stuck in a failed state.
- **FR-011**: Guide generation MUST be best-effort and non-blocking: requesting a guide MUST NOT block the page, and failures MUST surface a clear, retryable status rather than an opaque error.
- **FR-012**: Users MUST be able to view the content of a downloaded guide from the Class Guides tab.
- **FR-013**: Concurrent requests for the same class+spec MUST deduplicate to a single generation.
- **FR-014**: Manual guide generation MUST be rate-limited so a user cannot exhaust upstream data/model budgets, with clear feedback when throttled.

**Auto-fetch & reconciliation (US3)**

- **FR-015**: Saving the self character or adding a friend MUST continue to auto-trigger its resolved spec's guide, now contributing to the shared library and reusing an existing guide instead of regenerating.
- **FR-016**: A character MUST surface the guide for its resolved spec from the shared library in the profile UI and in the assistant's standing context, as it does today; an unresolved spec attaches no guide and leaves behavior unchanged.
- **FR-017**: Removing a character MUST NOT delete shared spec guides.
- **FR-018**: Existing per-character guide content MUST migrate to / be superseded by the shared spec-keyed library with no user-visible loss of available guides.

### Key Entities *(include if feature involves data)*

- **Spec Guide (shared/global)**: a written guide for one class+spec. Attributes: class, spec, content, status (none/pending/ready/failed), last-updated. Identity is (class, spec). Shared across all users; contains only generic guide content, never user data.
- **Class/Spec Roster**: the complete, static reference set of classes and their specs used to populate the Class Guides list.
- **User Character (existing, adjusted)**: a self/friend character with its identity, self/friend relationship, and raid role (feature 007) — unchanged and per-tenant. Its guide is now the shared Spec Guide for its resolved spec rather than per-character content.
- **Profile Page / Tabs**: the dedicated UI surface hosting the Characters and Class Guides tabs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A signed-in user can reach the Profile page from the main app in a single action, and the page exposes 100% of the profile actions previously available in the modal.
- **SC-002**: The Class Guides tab lists 100% of classes and specs, each showing exactly one unambiguous status.
- **SC-003**: A user can manually request a guide for any spec and, on success, see it marked downloaded with viewable content; a previously failed guide can be retried and reaches a terminal ready/failed state (never permanently stuck) in 100% of attempts.
- **SC-004**: Generating a guide for a spec that is already ready triggers **zero** additional generations; adding a character of an already-ready spec attaches the guide with zero new generations.
- **SC-005**: A guide generated by one user is visible to another user for the same spec 100% of the time (shared library), while no per-tenant user data ever appears in the library.
- **SC-006**: Repeated rapid manual requests are bounded by a rate limit and produce clear feedback rather than cascading failures.
- **SC-007**: Users rate the new page's clarity/appearance as a clear improvement over the modal (qualitative review), and all controls are operable via keyboard and clearly labeled.

## Assumptions

- **Guide content is non-user data**: class/spec guides are generic advice, so a global shared library is acceptable and does not weaken feature-006 isolation; all genuinely user-owned data (characters, friends, guild, raid roles, conversations) stays strictly per-tenant.
- **Any authenticated user may trigger generation**: manual requests and retries are available to any signed-in user (not admin-only), bounded by a rate limit.
- **Modal is replaced, not duplicated**: the dedicated page supersedes the profile modal; a navigation entry routes to it.
- **Reuse existing generation + context mechanisms**: the established background, non-blocking guide generation and the assistant's standing-context preamble are reused and extended to read from the shared library; the spec→role mapping and spec resolution from prior phases are reused.
- **Migration over loss**: existing per-character guides are migrated into the shared library (keyed by their class+spec) so no currently-available guide disappears.
- **Desktop-primary**: desktop remains the primary target; narrow layouts stay usable, consistent with prior phases.
- **Builds on prior phases**: assumes features 005 (profile/guides/context), 006 (multi-tenancy/auth), and 007 (captured metadata, findings reports, raid roles) are in place.
- **Scope boundary**: this feature does not change the agent's analytical tools, the chat experience, or report generation beyond reading guides from the new shared library.
