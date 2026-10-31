# Data Model: Crucial epic-203 QA fixes

No table, column or migration changes. The stored and returned shapes stay as 029/031 defined
them (`ProfileProposalOut`, `ProposalItemOut`, `ProposalValidation`, `ProposalDecisionOut`).

## ProfileChangeIn (agent input, `backend/app/schemas.py`)

Fields unchanged. New input normalisation (before validation; JSON schema unchanged):

| Field | Rule |
|---|---|
| `raid_role` | String → stripped, lower-cased. Still not `tank`/`healer`/`dps` → validation fails → row skipped `invalid_item`. |
| `played_role` | String → stripped, lower-cased. Still not a known role → `None` (display-only; item stays valid). |

## Proposal item input (tool → service)

`changes: Sequence[ProfileChangeIn | object]`: ADK may pass any element as a raw value.

Per element, in order (first match wins, one code per row):

1. realm missing / `None` / blank string → skipped `invalid_realm`
2. region missing / `None` / blank string → skipped `invalid_region`
3. not a `ProfileChangeIn` and `ProfileChangeIn.model_validate` fails → skipped `invalid_item`
4. the existing `_check` rules (CharacterIn → `invalid_item`, name/realm/region patterns,
   duplicates, limits, not_found, no_change)

Row for a skipped unparseable element (display only, never applied): `index` kept; strings taken
from the raw value when they are strings (clipped), else `""`; `action`/`target` the raw value if
allowed, else `add`/`friend`; roles `None`.

## Proposal decision (state transition)

```text
pending --approve (row lock)--> applied     [hook: save follow-up line, same transaction]
pending --cancel  (row lock)--> cancelled   [hook: save "Cancelled…" line, same transaction]
pending --(ttl passed)--------> expired     [no hook; approve → 409 proposal_expired]
applied   --approve--> applied (no-op, no hook)    applied   --cancel--> 409 proposal_applied
cancelled --cancel --> cancelled (no-op, no hook)  cancelled --approve--> 409 proposal_cancelled
```

## Turn conversation (frontend, `App.tsx`)

`turnConvRef: string | null`: set to the send's conversation id in `sendText`, then to the
`meta` frame's `conversation_id`. Read on `done`/`error` to decide whether the turn's proposals
belong to the open chat.
