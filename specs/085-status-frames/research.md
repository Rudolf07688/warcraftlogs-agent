# Research: 085 status frames and turn costs

## R1 Where BUG-004 happens
- Decision: clear `tokens` before `await _send(ws, InterimFrame)`.
- Rationale: the cancel lands on that await; the old order left `tokens` uncleared, and the superseded handler saved them. Whether the frame reached the browser is unknowable at that point; the runner's verdict (this was progress) is not.
- Alternatives: `asyncio.shield` the send and inspect the result (still ambiguous mid-transport, more code); keep send-first (the bug).

## R2 SEC-002 residual (interim lost in transit)
- Decision: on `WebSocketDisconnect` after a retraction with no tokens kept, persist "(no response)" as the partial.
- Rationale: `App.reloadAfterDrop` re-appends the local partial only when the server stored no agent message (meant for a server restart). Storing a row makes the reload show the server's state. The PDF is rendered server-side from stored messages (`downloadMessageReport`), so stored = PDF = reopened.
- Alternatives: store the retracted text on drops (shows troubleshooting text as an answer, the finding's concern); a boot id so the client can tell a restart (new handshake frame, more scope); never re-append (loses sc-376's restart case).
- Kept signature: tests patch `_persist_partial(conv_id, tokens, identity, user_seq)` positionally (test_052, test_076), so the placeholder is passed as the token list, not a new keyword.

## R3 NaN in retry frames
- Finding: `ModelRetryFrame(wait_s=nan).model_dump(mode="json")` keeps `nan`; Starlette `send_json` uses `json.dumps` (allow_nan) → bare `NaN`; browser `JSON.parse` throws in `onmessage`, the frame is lost.
- Decision: ws.py builds the frame with `wait_s` finite and ≥ 0 (else 0.0), `attempt`/`max_attempts` ≥ 0. Shape unchanged.

## R4 Status store
- Decision: `statusStore` with `{status, thought, notice, quietSince}`, `useSyncExternalStore`, immutable snapshots replaced only on change. `LiveMessage` subscribes; `MessageList` loses its `status/thought/quietSince` props.
- Rationale: same as PERF-010's `streamStore`. App keeps `streaming` and `streamCards` state (tool frames are rare and do change the list).

## R5 Narrow preamble read
- Decision: `repo.get_main_selection(session, *, tenant_id) -> tuple[str | None, str | None]` selecting `ProfileSettings.main_class, ProfileSettings.main_spec` with the tenant predicate (RLS also applies on Postgres).
