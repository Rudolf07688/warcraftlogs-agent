# Tasks: Crucial epic-203 QA fixes (profile proposals)

**Input**: `specs/034-epic203-qa-fixes/` (plan.md, spec.md, research.md, data-model.md,
contracts/internal-interfaces.md, quickstart.md)

**Tests**: Required. The plan's ACs name the tests (AC 1–6, clarification Q3).

**Gate**: No task below runs before the scrum master relays **OWNER GO** and the ownership grant.
GitNexus `impact` before each symbol edit (plan.md table); restore `CLAUDE.md` and
`.specify/feature.json` before every commit.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Re-index the worktree (`node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --index-only` in `/home/rudolf/dev/wcl-worktrees/dev-b`) and record a green baseline: `uv run --extra test pytest -q` (note pre-existing failures, if any) and `cd frontend && npm test && npm run build`

No foundational phase: the three stories touch disjoint code (US1 and US2 share
`backend/app/services/profile_proposals.py`, so they run one after the other).

---

## Phase 2: User Story 1 — One bad row never sinks the whole proposal (P1) · sc-241

**Goal**: any malformed item becomes one skipped row with the right code; roles are
case-insensitive; an unexpected tool failure is a plain `{"status": "error"}`.

**Independent test**: `uv run --extra test pytest -q backend/tests/test_profile_tools.py backend/tests/test_profile_proposals.py`

### Tests (write first, see them fail)

- [X] T002 [US1] In `backend/tests/test_profile_tools.py` add `test_raw_items_through_function_tool_become_skipped_rows` (AC 1, clarification Q1): build `FunctionTool(propose_profile_changes)` and `await tool.run_async(args={"changes": [realm None, region "", action "promote", played_role "Healer", one valid]}, tool_context=_ctx(...))`; assert `status == "success"`, codes `["invalid_realm", "invalid_region", "invalid_item", None, None]`, row 3 `played_role == "healer"`, stored proposal has 5 items, `_counts == (0, 1)`
- [X] T003 [US1] In `backend/tests/test_profile_tools.py` add `test_unexpected_failure_is_a_plain_tool_error` (AC 2): monkeypatch `profile_proposals.create_proposal` to raise `RuntimeError("boom secret")`; assert the result is `{"status": "error", "error_message": <plain>}` with no "boom"/"RuntimeError" in it; extend the scripted-turn test pattern so a turn whose tool raises still yields the scripted final text (turn continues)
- [X] T004 [P] [US1] In `backend/tests/test_profile_proposals.py` extend `test_bad_realm_region_and_schema` cases: `realm=""`, `realm="  "` → `invalid_realm`; `region=""` → `invalid_region`; keep `name=""` → `invalid_item`; add `test_raw_items_are_validated_one_by_one` (dicts with realm `None`, missing region, `target="guild"`, `name=None`, a bare string, a valid dict → codes `invalid_realm, invalid_region, invalid_item, invalid_item, invalid_item, None`; indexes 0–5 kept; skipped rows' strings clipped) and `test_roles_compare_case_insensitively` ("Healer"/"DPS"/" TANK " accepted and stored lower-case; unknown `played_role` "Support" → `None` and item valid; unknown `raid_role` "Support" → `invalid_item`)

### Implementation

- [X] T005 [US1] In `backend/app/schemas.py` (`ProfileChangeIn` only) add a `field_validator("raid_role", "played_role", mode="before")`: strings stripped and lower-cased; an unknown `played_role` → `None` (research R3). Confirm the declaration test still passes (schema unchanged)
- [X] T006 [US1] In `backend/app/services/profile_proposals.py`: add `_blank(value)` and a per-item `_parse(raw) -> tuple[ProfileChangeIn | None, str | None]` (blank/missing realm → `invalid_realm`, region → `invalid_region`, then `ProfileChangeIn.model_validate` for non-models → `invalid_item`); add the display row for an unparseable element (research R4: strings clipped with `_CLIP`, action/target fallback `add`/`friend`); make `_check` return `invalid_realm`/`invalid_region` for blank values before the `CharacterIn` check; `_validate` and `create_proposal` take `Sequence[ProfileChangeIn | object]`; `_apply` (typed re-validation) unchanged in behaviour
- [X] T007 [US1] In `backend/app/agent_tools/profile_tools.py` add the catch-all after the known branches: `logger.exception(...)` and return `{"status": "error", "error_message": "Couldn't prepare the profile changes. Tell the user to try again."}`; add a one-line note that ADK may hand over an item it couldn't convert as a raw value (the service validates each)
- [X] T008 [US1] Run `uv run --extra test pytest -q backend/tests/test_profile_tools.py backend/tests/test_profile_proposals.py backend/tests/test_proposal_ws.py`; all green

**Checkpoint**: sc-241 done and verified on its own.

---

## Phase 3: User Story 2 — Approving twice still tells the truth once (P1) · sc-242

**Goal**: only the call that moves a proposal out of `pending` (decided under `FOR UPDATE`)
saves the follow-up line, in the same transaction; no 500 on overlap.

**Independent test**: `uv run --extra test pytest -q backend/tests/test_proposal_routes.py` +
the Postgres run in quickstart.md §2.

### Tests

- [X] T009 [US2] In `backend/tests/test_proposal_routes.py` add `test_only_the_transitioning_call_saves_the_line` (SQLite): call `proposals.execute_proposal(identity, id, on_transition=spy)` twice → spy called once; same for `cancel_proposal`; and `test_a_failing_follow_up_rolls_the_decision_back` (hook raises → proposal still `pending`, profile unchanged, no line)
- [X] T010 [P] [US2] Create `backend/tests/test_proposal_race_pg.py` (skips unless `TEST_DATABASE_URL` starts with `postgresql`, like `test_rls.py`): point `backend.app.db.session.SessionLocal` at the Postgres sessionmaker; seed a tenant, user and conversation (as the app's provisioning helpers do) and a pending 2-item proposal; `asyncio.gather` two `routes.approve(proposal_id, identity)` calls → both return `ProposalDecisionOut`, exactly one `follow_up`, exactly one new agent message in the conversation, both friends added once; same for two `routes.cancel(...)` on a fresh proposal (one "Cancelled…" line); no guide tasks (monkeypatch `schedule_character_guide`); a fresh user and tenant per test (throwaway database), plus a rollback test (failed follow-up → nothing applied)

### Implementation

- [X] T011 [US2] In `backend/app/services/profile_proposals.py` add `TransitionHook` and the keyword-only `on_transition` parameter to `execute_proposal` and `cancel_proposal`; await it inside the locked `tenant_scope` transaction, after status/results are set, only on `pending → applied` / `pending → cancelled` (contracts/internal-interfaces.md)
- [X] T012 [US2] In `backend/app/api/proposals.py` rewrite `_decide`: no pre-lock `get_proposal`; pass a hook that `repo.add_message(...)`s `follow_up_text(proposal)`, refreshes it and keeps the `MessageOut`; return it as `follow_up` (null when the hook didn't run); expired handling and error codes unchanged; update the module docstring line about "only the call that left pending"
- [X] T013 [US2] Run `uv run --extra test pytest -q backend/tests/test_proposal_routes.py backend/tests/test_profile_proposals.py`; then the Postgres run (quickstart.md §2, container `wcl-034-pg` on port 15434) and keep its output for the hand-off

**Checkpoint**: sc-242 done; Postgres overlap test passes (not skipped).

---

## Phase 4: User Story 3 — Card in its own chat, honest status (P2) · sc-243

**Goal**: a turn's proposals attach only in the chat that produced them; the profile tool has its
own status label and spell.

**Independent test**: `cd frontend && npm test && npm run build`

### Tests

- [X] T014 [P] [US3] Create `frontend/src/App.test.tsx`: mock `./api/wsClient` (`ChatSocket` captures the frame handler; `send` returns true), `./api/restClient` (`getModels`, `listConversations`, `getRaids`, `getConversation` per id, `getGreeting`), `./auth/useAuth`, `react-router-dom`'s `useNavigate`, and the children `Sidebar` (buttons to select chat A/B and New chat), `MessageList` (renders per-message proposal ids, loose proposal ids and `status`), `Composer`, `WelcomePanel`, `Ambient`, `ModelSelect`. Cases: (a) turn in A, switch to B, `done` → B shows no card; (b) same with `error` → no loose card in B; (c) New chat mid-turn → no card; (d) switch away and back to A mid-turn (getConversation returns the proposal with `message_seq: null`), then `done` → card once (attached, no loose duplicate); (e) no switch → attaches as before; (f) `tool_start` `propose_profile_changes` → status "Preparing profile changes"; (g) `spellFor("propose_profile_changes") !== DEFAULT_SPELL`

### Implementation

- [X] T015 [P] [US3] In `frontend/src/toolLabels.ts` add `propose_profile_changes: "Preparing profile changes"`
- [X] T016 [P] [US3] In `frontend/src/lib/spells.ts` add a `propose_profile_changes` entry (icon `GiScrollQuill`, hue `GOLD`, verb "Inscribing the changes", two flavor lines), in a "Profile" group comment
- [X] T017 [US3] In `frontend/src/App.tsx`: add `turnConvRef`; set it in `sendText` (the send's conversation id) and in the `meta` handler (`f.conversation_id`); in `done` attach `pendingProposalsRef` only when `turnConvRef.current === activeIdRef.current` and then drop loose cards with the same ids; in `error` add orphans as loose cards only under the same condition (deduplicated by id)
- [X] T018 [US3] Run `cd frontend && npm test && npm run build` (typecheck included); all green

**Checkpoint**: sc-243 done.

---

## Phase 5: Polish & hand-off

- [X] T019 Full suites: `uv run --extra test pytest -q` (no new failures vs T001) and `cd frontend && npm run build && npm test`
- [X] T020 GitNexus: `node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --index-only` then `detect-changes --scope all --repo .` in the worktree (re-run if `partial`/`truncated`); check `git diff --name-only b963463...HEAD` + uncommitted lists only granted files; restore `CLAUDE.md` and `.specify/feature.json`; commit
- [X] T021 Hand-off to the scrum master: branch, base, commits, files, test output (incl. the pasted Postgres run), risks, AC mapping (plan AC 1 → T002, AC 2 → T003, AC 3 → T009/T010, AC 4/5 → T014, AC 6 → T019)

## Dependencies & order

- T001 → everything.
- US1 (T002–T008) → US2 (T009–T013): same service file; T010 can be written in parallel with US1.
- US3 (T014–T018) is independent of US1/US2 (frontend only) and can run in parallel with them.
- T019–T021 after all stories.

## Parallel example

```text
Developer (backend, sequential): T002–T008, then T009, T011–T013
Sub-agent A (frontend, parallel): T014–T018
T010 (new file) can be written by the developer while US1 tests run.
```

## Implementation strategy

MVP = US1 (the crash). Then US2 (data truth), then US3 (frontend guard; first to drop if the
sprint runs late, per the plan's drop order). Each story is committed after its checkpoint.
