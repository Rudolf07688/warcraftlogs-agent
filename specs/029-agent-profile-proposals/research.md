# Research: Capability Summary and Profile Proposal Tools (029)

The agreed design (`documentation/designs/self-aware-agent/capabilities-and-tools.html`, C1–C14)
settles the architecture. This file records only what the design left to 029, what was
checked against the base (1da8bca, code-identical to cf370e8), and the refinements that
check forced. Each entry: Decision / Rationale / Alternatives.

## R1 — ADK declaration for `changes: list[ProfileChangeIn]` (design C5 "Inferred")

- **Decision**: Keep the typed `list[ProfileChangeIn]` parameter. The string fields have no
  length constraints. Only `action`, `target`, `raid_role` and `played_role` are `Literal`s.
  Per-item length and identity checks run inside the service, so one bad item never fails
  the whole call.
- **Rationale**: A prototype on the base ADK (scratch script, not committed) built the
  declaration through `FunctionTool._get_declaration()`. It came out as
  `parameters_json_schema` with `$defs/$ref`, and
  `anthropic_llm.function_declaration_to_tool_param` turned it into a valid Claude
  `input_schema`. `tool_context` is excluded from both. ADK validates arguments with
  `pydantic.TypeAdapter` before the call (`function_tool.py:215–243`). A validation error
  goes back to the model as an error dict, so the model can correct the call. Length limits
  on the fields would turn one hostile 500-character name into a whole-call failure, which
  defeats "show it as skipped" (D4, C14).
- **Alternatives**: `list[dict]` validated inside the tool (the design's fallback). Not
  needed, because both declaration paths work. A unit test pins both declarations.

## R2 — Who is acting inside the tool (C7)

- **Decision**: `current_identity: ContextVar[RequestIdentity | None]` in
  `backend/app/tenancy/context.py` (default `None`). `_handle_turn` sets it next to
  `set_refresh_actor(...)` (ws.py:265). The tool requires
  `identity is not None and str(identity.tenant_id) == tool_context.user_id`. The
  conversation is `uuid.UUID(tool_context.session.id)`.
- **Rationale**: `stream_response` is an async generator iterated in the socket task, and it
  creates the producer task inside its own body (agent_runner.py:182–201). The producer
  therefore copies a context that already holds the identity. `ReadonlyContext.user_id` and
  `.session` exist in ADK 2.10 (`readonly_context.py:62–69`).
- **Shared runner (greeting, guide and guild-summary flows)**: these run the same agent
  through `stream_response` with `user_id="local_user"` and session ids `greeting-…` /
  `guide-<hex>` (`backend/app/greeting.py:52`, `backend/app/services/guide.py:174`). The tool
  needs all three of: an identity, a tenant match with `tool_context.user_id`, and a session
  id that parses as a UUID. The service also checks that the conversation belongs to that
  tenant. In those flows it therefore always fails closed and stores nothing (tested). The
  can-change line says Barnaby proposes changes *when the user asks*, so a guide or summary
  prompt has no reason to call it. **Decision**: keep one runner per model (design C6). The
  alternative was registering `PROFILE_TOOLS` only for chat turns: a second runner per
  model, picked in `stream_response` by `user_id != USER_ID`. It changes the HIGH-risk
  `_get_runner` and splits the cached prefix, for a model-behaviour risk no offline test can
  measure. It remains the fallback if the live check shows guide text mentioning profile
  changes.
- **ws.py footprint**: one statement, `current_identity.set(identity)`. The existing import
  line 28 (`from ..tenancy.context import RequestIdentity, apply_tenant_scope, tenant_scope`)
  gains `current_identity`. That is two changed lines in total, both in the 029 grant.

## R3 — Capability summary shape (C1–C4, D13)

- **Decision**: `wcl_agent/capabilities.py` provides `ToolGroup(label, tools, note="")`,
  `render_capability_summary(groups, *, web_search: bool) -> str`,
  `CAPABILITY_SUMMARY_MAX_CHARS = 4000` and `MAX_TOOL_LINE_CHARS = 160`. Output order:
  1. the fixed usage rule (only exposed tools; issue independent calls in parallel);
  2. per group, a `Label:` header, plus ` (note)` when the group has a note, then one
     `- name: first paragraph` line per tool;
  3. when `web_search` is false, the line "No web search in this session: say current-patch
     verification was not possible.";
  4. when any registered group has a note (only the backend's profile group does), the
     "You can change …" line and the D13 "In the app …" line;
  5. the "You cannot …" line, which is always present. Its wording depends on whether the
     profile group is present.
- **Name/description source**: `FunctionTool(fn).name/.description` for functions, and
  `.name/.description` for `BaseTool` instances (the `web_search` `AgentTool`). The first
  paragraph is whitespace-collapsed. When it is longer than the 160-character line budget,
  it is cut at the last sentence end that fits.
- **D13 line (checked against `frontend/src` on the base)**: "In the app (the user does these
  themselves): the Profile page (own characters, friends, main guild, raid roles; Class
  guides tab), recent raids and Mythic+ runs on the welcome screen, PDF download of a reply,
  boss checkboxes under a report to focus the next question, and the model picker."
  Sources: `pages/ProfilePage.tsx` (Characters and Class guides tabs),
  `components/WelcomePanel.tsx`, the `MessageList.tsx` PDF button, `EncounterPicker.tsx`,
  `ModelSelect.tsx`. The base has no separate Raids page (routes are `/app`, `/profile`,
  `/admin/users`) and no per-chat character filter (sc-144 isn't built).
- **Prototype**: the first paragraphs of the 20 WCL tool docstrings come to 1,876 characters,
  every line is ≤ 106 characters, and none contains `{`/`}`. The full summary is estimated
  at about 3,100 characters, under the 4,000 budget.
- **Alternatives**: the absent-web-search line and the boundary lines in `agent.py`. They are
  rejected because the renderer is the one place that knows what the summary contains (and
  `capabilities.py` must not import `agent.py`, which would be a cycle).

## R4 — Wiring into the instruction (C2) and the module snapshot

- **Decision**: `_INSTRUCTION_BODY`'s `<TOOLS>` body becomes the token `@@CAPABILITIES@@`.
  `build_instruction(ctx=None, *, capabilities: str = "")` replaces both tokens.
  `build_agent(model, retry=None, *, extra_groups=())` assembles
  `groups = [*TOOL_GROUPS, *extra_groups, (web group if Gemini)]`, renders once, and passes
  `instruction=functools.partial(build_instruction, capabilities=summary)` and
  `tools=[t for g in groups for t in g.tools]`. `TOOLS` stays as the flattened
  `TOOL_GROUPS`, for the existing imports (`test_tool_concurrency.py`). `INSTRUCTION` moves
  below `root_agent` and becomes `root_agent.instruction(None)`, the CLI/Gemini snapshot.
- **Refinement of the design's test "no registered tool name appears literally in
  `_INSTRUCTION_BODY`"**: other sections must name tools, and existing tests require it
  (`BENCHMARK_POLICY`: `compare_player_to_cohort`; `COACHING_POLICY`: `get_cooldown_usage`;
  `COACHING_BRIEFS`: `get_coaching_brief`). The check therefore applies to the fixed
  `<TOOLS>` section of `_INSTRUCTION_BODY`, which is the hand-written tool list sc-204
  removes.
- **Tests that change in `test_prompt_contract.py`**:
  - `test_every_registered_tool_is_described`: every `TOOLS` name is in the generated
    `<TOOLS>` section.
  - `test_web_search_described_as_optional`: the Gemini summary lists `web_search`, and the
    Claude summary says it is not available.
  - `test_cooldown_tool_takes_content_type`: `content_type` is in the `get_cooldown_usage`
    docstring.
  - `test_agent_uses_the_instruction_provider`: the instruction is a `partial` of
    `build_instruction` bound to the agent's summary.

  Every other clause test stays as it is.

## R5 — Validation semantics (C12, C13)

- **Decision**: one validator, `_validate(items, own, friends)`, is used both at creation
  and when an item is re-validated at execution. It walks the items in order over a working
  copy of the profile:
  1. `CharacterIn` (name, server = realm, region, raid_role) → `invalid_item`.
  2. The identity rules → `invalid_name` / `invalid_realm` / `invalid_region`.
  3. The action rules:
     - add: an existing identity in the same target → `duplicate_character` /
       `duplicate_friend`; in the other target → `already_friend` / `already_own`; added
       earlier in this proposal with the same target → `duplicate_item`; a limit →
       `character_limit` / `friend_limit`.
     - update/remove: not in that target → `not_found`; an update to the same role →
       `no_change`.
     - Repeated update/remove of the same identity and target → `duplicate_item`.

  Each valid item updates the working copy (an add inserts, a remove deletes), so limits
  count ahead. A "move" (remove a friend, then add the same identity as own) validates
  correctly, as the design's follow-up expects.
- **Identity key**: `(name.casefold(), server_slug(realm), region.lower())`, using the
  existing `wcl_agent.cache.normalize.server_slug`.
- **Identity rules** (one place, `profile_proposals.py`):
  - name `^[^\W\d_]{2,12}$`;
  - region in `{us, eu, kr, tw, cn}`;
  - realm: 2–40 characters of letters, digits, spaces, apostrophes, hyphens **and
    parentheses**, starting with a letter or digit.

  Parentheses are added because real EU realms carry them (e.g. "Aggra (Português)"). The
  design says the pattern widens in one place, and the hostile-name guard is the name rule.
- **Clip**: the stored and returned `name`/`realm` of an item are clipped to 100 characters
  (the `CharacterIn` maximum). An over-long value is invalid anyway, and clipping bounds the
  row and the tool result.
- **Region** is stored lower case on apply. Identity comparison was already
  case-insensitive, so existing upper-case rows keep matching.

## R6 — Execution transaction (C11)

- **Decision**: `execute_proposal` opens
  `tenant_scope(identity.tenant_id, user_id=identity.user_id)`. It loads the row with
  `with_for_update()`, filtered on id, tenant and user (a miss → `not_found`). Then:
  - `applied` → return it unchanged.
  - `cancelled` → `proposal_cancelled`.
  - expired → store `expired`, leave the transaction normally so it commits, then raise
    `proposal_expired` after the `async with`. `tenant_scope` rolls back on an exception,
    so the raise must happen outside it.
  - Otherwise, re-validate the originally valid items against the live profile and apply
    each still-valid one inside `session.begin_nested()` through `profile_service`. A
    `CharacterConflict`, `CharacterNotFound` or `IntegrityError` marks that item `failed`.
    Items get their results, the `items` JSON is reassigned (so the change is detected),
    the status becomes `applied` with `applied_at`, and the proposal commits once.

  After the commit, `profile_service.schedule_guides(added_ids, tenant_id)` runs.
- **Re-validation addresses update/remove by identity** against the live profile, not by the
  stored `character_id`. A character removed and re-added by hand in between is still found.

## R7 — Storage helpers

- **Decision**: a new `backend/app/repositories/profile_proposals.py`, following
  `repositories/raw_fetches.py` and `invitations.py` (`for_update`). It holds
  `insert_proposal`, `get_proposal_row(…, for_update=False)` and `list_proposal_rows`, each
  filtering on `tenant_id` and `user_id`.
- **Rationale**: `backend/app/db/repository.py` is a 1,000-plus-line shared module that 030
  and 031 also touch. Keeping the proposal queries out of it limits 029's edits there to the
  D8 cap and the C12 slug comparison.

## R8 — Friend-limit message (D8)

- **Decision**: in `CharactersTab.tsx`, `case "friend_limit": return "You've reached the
  friend limit. Remove a friend before adding another.";`. The message carries no number.
- **Rationale**: `ProfileOut` exposes only `own_limit`. Hard-coding "50" in the frontend
  would be a second source for `MAX_FRIENDS` (Principle I), and adding `friend_limit` to
  `ProfileOut` would touch `types.ts` (031's file) for no requirement. No component is
  added, so shadcn has nothing to search (Principle VII applies to components; this is one
  string).

## R9 — Offline scripted agent test (D11-4, design Tests "Agent-eval")

- **Decision**: in `test_profile_tools.py`, a test-local `_ScriptedLlm(BaseLlm)` drives one
  turn. The first response is a `propose_profile_changes` function call (a hostile name plus
  valid items), and the second is plain text. The test builds the backend agent through
  `build_agent(model, extra_groups=(PROFILE_TOOLS,))`, replaces `agent.model`, and runs a
  real `Runner` on an `InMemorySessionService`, with `current_identity` set and the SQLite
  `SessionLocal` patched. It asserts the tool result, the stored proposal (hostile item
  `invalid_name`) and that `user_characters` is unchanged.
- **Rationale**: no network, real ADK tool dispatch and argument validation. The `before_model`
  callback is a no-op without a turn in `current_turn`.

## R10 — Migration and RLS checks (AC 7)

- **Decision**: three checks.
  - A SQLite test runs 0016 `upgrade()`/`downgrade()` through Alembic `Operations`, as
    `test_recent_mplus.py::test_migration_0014_upgrades_and_downgrades` does.
  - A Postgres-only test is skipped without `TEST_DATABASE_URL`. It mirrors `test_rls.py`
    for `profile_proposals`: no rows without context, no cross-tenant select, and an insert
    for another tenant is rejected.
  - A manual run on a throwaway Postgres at port 15429 (`docker run`, dummy credentials):
    `alembic upgrade head`, `downgrade -1`, `upgrade head`, plus the Postgres tests under
    the runtime role. It is recorded in `quickstart.md` and in the hand-off.

## Baseline

`uv run --extra test pytest -q` on 1da8bca (code-identical to cf370e8): **1066 passed,
3 skipped, 1 deselected** in 72 s.
