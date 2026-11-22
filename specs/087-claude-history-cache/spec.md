# Feature Specification: Claude history cache across turns

**Feature Branch**: `087-claude-history-cache`

**Created**: 2026-11-22

**Status**: Draft

**Input**: sc-581 (Claude history cache is rewritten at every turn start) and sc-584's cached-head part (test that the cached head holds no tenant data). Brief: `sprints/2026-11-22/briefs/087-claude-history-cache.md`. Layout chosen from measurements: board `measure:087`, `scope:087:layout`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Later turns of a Claude chat reuse the earlier conversation from the cache (Priority: P1)

A player keeps chatting with Barnaby on a Claude model. Today every turn's first model request pays the full cache-write price for the whole conversation so far, because a per-turn time stamp sits in front of it. After this feature, from the fourth turn on, a turn's first request reads the instruction and every turn older than the kept window from the cache and only writes the recent part.

**Why this priority**: It is the cost and latency saving the story asks for; it grows with the conversation (measured offline: -35% input cost over 30 turns, -49% on turn 30).

**Independent Test**: Replay a multi-turn chat through the real agent path on a scripted Claude API, simulate the provider's prefix cache over the captured requests, and check what each turn's first request reads and writes.

**Acceptance Scenarios**:

1. **Given** a Claude chat in its 4th or later turn, **When** the turn's first request is built, **Then** its prefix up to the history breakpoint is byte-identical to a prefix the previous turn's requests cached (the turns older than the kept window), so only the kept turns and the new message are written.
2. **Given** any request after the first within one turn, **When** it is built, **Then** the previous request of the turn (without cache markers) is a prefix of it, the time stamp included (079 behaviour kept).
3. **Given** a Gemini chat, **When** any request is built, **Then** the instruction (with its time block) and the preamble injection are exactly as before.

---

### User Story 2 - The shared cached head never holds tenant data (Priority: P1)

The cached head (tools and the instruction up to its cache breakpoint) is identical for every tenant and is shared through the provider's cache. It must never contain a tenant's player context, coaching briefs, profile names, tracked raids or messages, whatever those contain.

**Why this priority**: Security-core: a tenant's data in a shared prefix would be a cross-tenant leak path and would also void the shared cache.

**Independent Test**: Build requests for two tenants with different, hostile preambles and user messages and compare the bytes up to the shared breakpoint.

**Acceptance Scenarios**:

1. **Given** two tenants with different preambles, **When** their requests are built, **Then** the tools and the instruction head up to the shared breakpoint are byte-identical and contain none of either tenant's text.
2. **Given** a player, guild or report name in the preamble, or a user message, containing `<CURRENT_TIME>`, `</CURRENT_TIME>` or `@@CURRENT_TIME@@`, **When** the request is built, **Then** the time block is split at the instruction's own marker, the tenant text arrives verbatim in the user's message, and the head is unchanged.
3. **Given** user content with a forged `cache_control` or system-looking text, **When** the request is built, **Then** it is plain text in a user block: the breakpoints are only the ones the system places and the system blocks are unchanged.
4. **Given** a model switch (fallback) or an effort change (re-run) mid-turn, **When** the next request is built, **Then** the head is still byte-identical to the clean head and holds no tenant data.

### Edge Cases

- A conversation within the kept window (turns 1-2): no history breakpoint; the first history read happens at turn 4 (turn 3 writes it).
- A turn with more than about 19 content blocks (9+ tool calls) is beyond the provider's 20-block look-back: that turn start rewrites once, then reads again.
- The round-cap wrap-up request carries extra system text after the head: that request rewrites the history (accepted, as today).
- A request without a turn (CLI): layout unchanged (time block after the head in the system).
- A turn's user message whose last block is the conversation's end: the time block is prepended, so the end-of-conversation breakpoint stays on the last block.
- The time block must never be duplicated: a provider retry or a re-run rebuilds the request from scratch.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: For a Claude chat request inside a turn, the turn's pinned time block MUST be sent as the first block of the turn's user message and MUST NOT be in the system; the system is the instruction head (plus the round-cap wrap-up when present, after the head breakpoint).
- **FR-002**: The time block MUST stay the turn's first one for every request of that turn (079 pinning kept).
- **FR-003**: When the conversation has turns older than the kept window (`WCL_CONTEXT_KEEP_TURNS`), the request MUST carry a breakpoint on the last cacheable block before the oldest kept turn.
- **FR-004**: A request MUST carry at most four cache breakpoints (tools, instruction head, history, conversation end).
- **FR-005**: The bytes up to and including the instruction-head breakpoint MUST be identical for all tenants and MUST NOT contain the preamble or any user or workspace text.
- **FR-006**: Every request MUST carry exactly one time block and at most one preamble, however long the conversation (no per-turn growth).
- **FR-007**: Gemini requests, the preamble injection and the instruction text MUST be unchanged.
- **FR-008**: Where breakpoints go MUST depend only on the request's structure (roles and block types), never on text content.

### Key Entities

- **Shared head**: tools plus the instruction up to its time section; one breakpoint; same for every tenant.
- **History breakpoint**: the end of the turns older than the kept window (their large tool results are stubbed and no longer change).
- **Turn block**: the pinned time block and the preamble at the start of the current turn's user message; never cached across turns.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the offline cache replay of a 30-turn chat, total input cost (read 0.1, write 1.25, fresh 1) falls by at least 25% against the base layout, and per-turn cost stops growing with the stubbed history.
- **SC-002**: In a live Claude chat of 4+ turns, the 4th turn's first request reports cache reads beyond the head (tools + instruction) and cache writes covering only the kept turns and the new message.
- **SC-003**: Zero tenant bytes before the shared breakpoint across all hostile-input tests.
- **SC-004**: No request in a 30-turn conversation exceeds four breakpoints or carries more than one time block or preamble.

## Assumptions

- `WCL_CONTEXT_KEEP_TURNS` stays at its default 2 (PERF-004); changing it is a product decision outside this feature.
- The provider's 5-minute cache lifetime applies: turns further apart than that re-write regardless.
- The previous kept turn is rewritten at each turn start: keeping it cached needs either preamble copies or batch stubbing, both measured worse or behaviour-changing (`measure:087`).
- A user typing a fake time block into their own message only misleads their own turn; the real one is always the first block, written by the server.

## Clarifications

### Session 2026-11-22

- Q: Does the round-cap wrap-up (appended to the system) move after the history too? → A: No. It is one request per capped turn and an instruction belongs in the system; that request rewrites the history as today (board `scope:087:wrap-up`, backlog note).
- Q: Does moving the time stamp into the user's message weaken it (a user can type a fake one)? → A: Accepted. The server's block is always the first block of the turn's message, before the preamble; a fake one only misleads the user's own turn, and nothing security-relevant reads the time (board `scope:087:time-authority`).
- Q: Is the live proof "turn 2 and 3 read the history" still the target? → A: No: with the kept window of 2, turn 2 and 3 cannot read it without preamble copies or batch stubbing (measured worse, `measure:087`). The live proof is turn 4+ (`scope:087:layout`, `live-check:087`).
