# Research: 031 confirmation card

Settled elsewhere, not repeated: transport (WS frame + REST), card parts, behaviour and labels,
follow-up wording, refresh channel and edge cases are in
`documentation/designs/self-aware-agent/participants-and-confirmation.html`. The proposal shape,
codes and service API are in `capabilities-and-tools.html#proposal-contract`. The decisions are in
`sprints/2026-10-26/decisions.md` (D4, D6, D8, D9, D10) and the spec's Clarifications (Q1, Q2). The
points below are the ones those documents leave to the implementer.

## R1 Linking a proposal to its answer at `done`

- **Decision**: `_handle_tool_end` returns the id of a proposal it sent as a frame (else `None`).
  `_handle_turn` collects them, and right after `repo.assign_message_seq_to_turn_captures(...)` (same
  session) calls `profile_proposals_repo.set_message_seq(session, ids, agent_msg.seq,
  tenant_id=…, user_id=…)`, a small `UPDATE … WHERE id IN ids AND tenant_id AND user_id AND
  message_seq IS NULL`.
- **Rationale**: The design's `#edges` says a proposal whose turn never reached `done` keeps
  `message_seq = null` and renders standalone. If proposals were added to the "stamp every
  unassigned row" update (the artifact pattern), the next successful turn would adopt them under the
  wrong answer. Collecting ids costs one list and a return value. The helper lives next to 029's
  other row helpers, tenant- and user-scoped like them.
- **Alternatives**: extend `assign_message_seq_to_turn_captures` (simplest, but breaks the
  failed-turn rule); stamp in `_handle_tool_end` with the user message's seq (wrong message:
  proposals belong under the agent answer).

## R2 When the follow-up line is saved

- **Decision**: `POST …/approve`: `before = get_proposal(identity, id)` (a `ProposalError` maps to
  HTTP); `after = execute_proposal(identity, id)`. If `before.status == "pending"` and
  `after.status == "applied"`, build the line from `after.items` and save it with
  `repo.add_message(session, after.conversation_id, "agent", line, tenant_id=…)` in a short
  `tenant_scope(identity.tenant_id, user_id=…)` opened only for that write (as ws.py does), and
  return it as `follow_up` (`MessageOut`). The design names `get_tenant_db`, but that would hold a
  second connection open while the service runs its own transaction, so the route uses
  `require_csrf` plus the short scope (same tenant RLS path, PERF-006).
  Otherwise `follow_up = null`. Cancel is the same, with `cancel_proposal` and the fixed line
  "Cancelled. Your profile is unchanged."
- **Rationale**: The design's REST table: "the route reads the status first and only saves a line
  when this call applied it". The two-clicks-in-the-same-millisecond case can save two lines; the
  design accepts that (the profile is still written once). Q2 = A: a second tab gets `null`.
- **Builder**: `follow_up_text(proposal) -> str`, a pure function in `api/proposals.py`, with
  `_LABELS` matching the card's map. Format (design `#followup`): applied adds per target ("Added 3
  friends: A, B and C."; "Added 1 of your characters: A."), removes ("Removed 1 friend: A."), updates
  ("Set A's role to healer." / "Cleared A's role." for `null`), then "Skipped N: A (label), B
  (label)." and "Couldn't add A (label)." for failed items. Prefixed "Done. " when nothing failed;
  suffixed " Nothing else changed." when something failed. "Nothing was applied." when no item
  applied.

## R3 Cancel of an expired proposal

- **Decision**: If `cancel_proposal` returns status `expired`, the route answers 409
  `proposal_expired` and saves no line.
- **Rationale**: The design's REST table lists `409 proposal_expired` for cancel. 029's service
  returns the expired proposal rather than raising, so the route does the mapping. Approve gets the
  same code from the service's `ProposalError("proposal_expired")`.

## R4 How the card treats errors

- **Decision**: `ApiError.message` carries the detail code (existing envelope: `HTTPException(detail=
  code)`, read like `CharactersTab.describeAddError`). 409 `proposal_expired` → status `expired`.
  409 `proposal_cancelled` → `cancelled`. 409 `proposal_applied` → `applied`. All are set locally;
  rows keep their last detail. Anything else (404, 5xx, network) → the alert "Couldn't apply. Try
  again." (cancel: "Couldn't cancel. Try again."), and the card is pending again.
- **Rationale**: "The card always shows what the server says": a 409 is the server's state. A GET
  route only to fetch per-item results after a lost race isn't worth it (YAGNI). The broadcast from
  the winning tab usually lands first anyway.

## R5 Bubble widths (sc-208, Q1 = A)

- **Decision**: In `frontend/src/styles.css`: `.message { max-width: min(90%, 1200px); min-width: 0;
  overflow-wrap: anywhere; }`, `.message.user { max-width: min(75%, 900px); }`, and the
  `.message.agent` `max-width` override is removed. `.welcome-panel { max-width: min(90%, 1200px); }`.
  `.markdown pre` and `.markdown table` already have `overflow-x: auto`.
- **Rationale**: A percentage of the flex column, with px caps like the rules they replace.
  `overflow-wrap: anywhere` stops one long URL or token from widening the page.
- **Verification**: headless Chrome on a `vite preview` build (port 18031) at 390, 1280 and 1920.
  `document.documentElement.scrollWidth <= innerWidth`, and the bubble's `getBoundingClientRect`
  width is checked against the caps.

## R6 Frontend test runner

- **Decision**: `vitest@^3.2.4` (its `vite` range `^5 || ^6 || ^7` fits the repo's Vite 5.4; vitest
  4/5 need Vite ≥ 6), `@testing-library/react@^16.3` with its peer `@testing-library/dom@^10.4`, and
  `jsdom@^26`. A separate `frontend/vitest.config.ts` (`defineConfig` from `vitest/config`, React
  plugin, `test.environment = "jsdom"`, `include: ["src/**/*.test.tsx"]`). Explicit imports from
  `vitest`, so `tsc -b` (which includes `src/`) typechecks the test without global types. The
  `restClient` calls are mocked with `vi.mock`.
- **Alternatives**: config inside `vite.config.ts` (mixes test config into the build config);
  happy-dom (lighter, but jsdom is what the design names).

## R7 Avatar reuse

- **Decision**: Move `ClassAvatar` out of `components/profile/CharactersTab.tsx` into its own
  `components/profile/ClassAvatar.tsx`, with its prop typed as `{ name: string; class_name: string |
  null }` (a `Character` still satisfies it), and use it in the card's `ItemMedia`. An export from
  CharactersTab would pull the whole lazy profile module into the chat bundle (measured +19 kB,
  PERF-011), so the shared module is the reuse that keeps the split (SM grant).
- **Rationale**: The design says "the same row style as the profile's character list". Reusing the
  component (not just `classColor`/`initials`) keeps one implementation (I). `CharactersTab.tsx` is
  029-held until merge, so this is an after-029 step. Until then the card's `ItemMedia` is left out,
  and the import is added in that step (no throwaway avatar).

## R8 Where standalone cards render

- **Decision**: `App` keeps `looseProposals` state: proposals with `message_seq == null` from a
  reload, plus the pending proposals of a turn that ended in `error`. `MessageList` takes it as a
  prop and renders them after the messages, before the live message.
- **Rationale**: `#edges` ("standalone card after the last message"; "on error, App.tsx keeps the
  turn's pending proposals"). It's stored as state, so `MessageList`'s memo holds.

## R9 Appending the follow-up line

- **Decision**: `ProposalCard` takes `onFollowUp(conversationId, message)`. `App` appends the message
  only when `conversationId === activeIdRef.current`. While a turn streams, the line lands before the
  live message, which matches the saved order (its seq is between the user message and the answer).
