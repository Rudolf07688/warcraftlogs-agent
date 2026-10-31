# Internal interfaces: Crucial epic-203 QA fixes

No external contract changes: REST routes, WS frames, `ProfileProposalOut` and the tool's
declared schema are unchanged. These are the internal interfaces the fix touches.

## Tool `propose_profile_changes` (model-facing)

- Declaration: unchanged (`changes: list[ProfileChangeIn]`; pinned by
  `test_declaration_has_no_identity_parameters_for_gemini_and_claude`).
- Runtime tolerance: any element may be a raw value (ADK pass-through); each becomes a row.
- Results:
  - `{"status": "success", "proposal": ProfileProposalOut, "note": …}`: unchanged.
  - `{"status": "error", "error_message": "<plain text>"}`: unchanged cases plus any unexpected
    exception (message: "Couldn't prepare the profile changes. Tell the user to try again.";
    never exception text; the exception is logged).

## Proposal service (`backend/app/services/profile_proposals.py`)

```python
TransitionHook = Callable[[AsyncSession, ProfileProposalOut], Awaitable[None]]

async def create_proposal(
    identity: RequestIdentity, conversation_id: uuid.UUID,
    changes: Sequence[ProfileChangeIn | object],
) -> ProfileProposalOut

async def execute_proposal(
    identity: RequestIdentity, proposal_id: uuid.UUID, *,
    on_transition: TransitionHook | None = None,
) -> ProfileProposalOut

async def cancel_proposal(
    identity: RequestIdentity, proposal_id: uuid.UUID, *,
    on_transition: TransitionHook | None = None,
) -> ProfileProposalOut
```

`on_transition(db, proposal)` runs inside the tenant-scoped transaction that holds the proposal's
`FOR UPDATE` lock, after the new status and per-item results are set, and only when this call
moved the proposal out of `pending`. If it raises, the whole decision rolls back. Errors raised
by execute/cancel are unchanged (`ProposalError` codes).

## Approve / cancel routes (`backend/app/api/proposals.py`)

Responses and codes unchanged (`ProposalDecisionOut`; 404 `not_found`; 409
`proposal_expired` / `proposal_cancelled` / `proposal_applied`). `follow_up` is non-null only on
the response of the call that made the transition.

## Chat frame handling (`frontend/src/App.tsx`)

| Frame | Before | After |
|---|---|---|
| `meta` | sets the open chat id when none is open | also records the turn's conversation id |
| `done` | proposals attach to the answer in the open chat | attach only if the turn's chat is open; drop a loose copy of the same proposal |
| `error` | proposals become loose cards in the open chat | only if the turn's chat is open (deduplicated) |
| `tool_start` (`propose_profile_changes`) | "Searching Warcraft Logs", default spell | "Preparing profile changes", its own spell |
