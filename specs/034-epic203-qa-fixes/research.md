# Research: Crucial epic-203 QA fixes

## R1 — How ADK passes a list item that fails conversion (sc-241)

- **Finding (verified on google-adk 2.10.0)**: `FunctionTool._preprocess_args` converts
  `list[ProfileChangeIn]` item by item; an item that fails `model_validate` is logged
  ("Failed to convert item in 'changes'…") and passed through **as the raw dict**.
  `FUNCTION_TOOL_ARG_VALIDATION` is off, so nothing rejects the call before the tool runs.
  Probe: `[{realm: None}, {played_role: "Healer"}, valid]` → `['dict', 'dict', 'ProfileChangeIn']`.
  `_check` then reads `change.name` on a dict → `AttributeError` escapes the tool → `agent_error`.
- **Decision**: Keep the annotation `list[ProfileChangeIn]` (the model keeps the item schema and
  enums; FR-002) and make the service tolerate any element: a model passes straight through,
  anything else is validated with `ProfileChangeIn.model_validate` per item; a failure becomes a
  skipped row.
- **Alternatives**: (a) annotate `list[dict]` (design C5 fallback) — loses the item schema the
  model sees, so worse arguments; (b) enable ADK's arg validation — rejects the *whole* call on one
  bad item, the opposite of FR-001; (c) widen `ProfileChangeIn` fields to `str | None` / plain
  `str` — changes the declared schema (realm/region no longer required, enums lost).

## R2 — Reason codes for blank or missing realm/region (sc-241, FR-003)

- **Decision**: A shared `_blank(value)` (None, missing, or a string of only spaces) is checked
  first, for both a parsed model and a raw mapping: realm → `invalid_realm`, then region →
  `invalid_region`. Only then does the generic parse/`CharacterIn` check run (`invalid_item`).
  Today blank realm hits `CharacterIn`'s `min_length` first and is coded `invalid_item`.
- **Order for several faults**: realm, region, then anything else. One code per row.

## R3 — Case-insensitive roles (sc-241, FR-004, clarification Q2)

- **Decision**: A `field_validator("raid_role", "played_role", mode="before")` on
  `ProfileChangeIn` strips and lower-cases strings. For `played_role` (display-only) a value that
  is still not a known role becomes `None`; for `raid_role` (stored) it is left as is, so the
  Literal rejects it and the item is skipped as `invalid_item`.
- **Why on the model**: ADK's own conversion then succeeds for "Healer"/"DPS", so those items stay
  typed models; a before-validator does not change the JSON schema (checked by the existing
  declaration test).

## R4 — Display values for an unparseable item

- **Decision**: The skipped row keeps the item's index; `name`/`realm`/`region`/`class_name`/
  `spec` are the raw value if it is a string (clipped to `_CLIP`, region lower-cased) else `""`
  (`None` for class/spec); `action`/`target` are the raw value if allowed, else `"add"` /
  `"friend"` (display only: the card shows a skipped row as "Skipped · not valid", and the
  follow-up never names an `invalid_*` item). Roles are `None`.
- **Alternative**: widen `ProposalItemOut.action/target` with an "unknown" value — a contract
  change for `frontend/src/types.ts` and the card; out of scope.

## R5 — Tool catch-all (sc-241, FR-007)

- **Decision**: After the known `ValueError` / `ProposalError` branches, `except Exception` logs
  with `logger.exception` and returns `{"status": "error", "error_message": "Couldn't prepare the
  profile changes. Tell the user to try again."}` (no exception text). The model sees a normal
  tool error and continues the turn; `ws.py` only sends a `proposal` frame on `status ==
  "success"`.

## R6 — One decision, one line (sc-242)

- **Finding**: `_decide` reads `before` in its own transaction, then calls the service; two
  overlapping calls both see `pending`. The service's `FOR UPDATE` makes the apply happen once,
  but both save a line; overlapping inserts collide on `uq_message_conv_seq` (`_next_seq` is
  max+1) → 500 after the change was applied.
- **Decision**: `execute_proposal(identity, id, *, on_transition=None)` and
  `cancel_proposal(identity, id, *, on_transition=None)`. Inside the locked transaction, only
  when this call moves the row from `pending` to `applied`/`cancelled`, they `await
  on_transition(db, out)`. The route passes a hook that `add_message`s `follow_up_text(out)` and
  captures the `MessageOut`. No pre-lock read remains. The second call waits on the row lock,
  then sees the committed status and returns the stored state without calling the hook. Because
  both inserts of one proposal now run under that proposal's row lock, they can't overlap.
- **All or nothing**: if the insert fails, the transaction (apply + status + line) rolls back
  (US2 AC 3).
- **Expired**: unchanged (no transition → no hook; the route still answers 409
  `proposal_expired`).
- **Alternatives**: return a `transitioned` flag and insert afterwards (not the same
  transaction, FR-009); a unique "one follow-up per proposal" constraint (needs a migration);
  retry on the seq conflict (masks the double line).

## R7 — Verifying sc-242 (clarification Q3)

- **Decision**: `backend/tests/test_proposal_race_pg.py`, skipped unless `TEST_DATABASE_URL` is a
  Postgres URL (same pattern as `test_rls.py`). It points `db_session.SessionLocal` at that
  database, seeds a tenant, user, conversation and pending proposal, and runs two `approve` route
  handlers concurrently (`asyncio.gather`), and separately two `cancel`s. Asserts: both succeed;
  exactly one carries `follow_up`; the conversation has exactly one new agent line; the friends
  were added once. A SQLite test in `test_proposal_routes.py` checks the hook runs only on the
  transition (a second approve/cancel saves nothing). The developer runs the Postgres test on
  their own container (port 15434) and pastes the output into the hand-off.

## R8 — Card in the right chat (sc-243)

- **Finding**: `done` attaches `pendingProposalsRef` to the message appended to whatever chat is
  open; `error` makes them loose cards there. The `meta` frame carries the turn's
  `conversation_id` but is only used when no chat is open.
- **Decision**: `turnConvRef` = the conversation the turn was sent to (`sendText`) and then the
  `meta` frame's id. On `done`/`error`, the turn's proposals are used only if `turnConvRef ===
  activeIdRef`; then any loose card with the same proposal id is removed (a mid-turn reopen
  loads the proposal as loose because its `message_seq` is still null). Otherwise they are
  dropped from the client; the server already links them to the answer (`message_seq`) and a
  reload of the chat shows them.
- **Out of scope** (ticket): the `done` answer text itself still lands in the open chat.

## R9 — Status label and spell (sc-243, SPEC-011)

- **Decision**: `TOOL_LABELS.propose_profile_changes = "Preparing profile changes"`; a spell
  entry with an existing `react-icons/gi` icon (`GiScrollQuill`, already imported) and hue
  `GOLD`, verb "Inscribing the changes", two flavor lines. No new icon import needed.
