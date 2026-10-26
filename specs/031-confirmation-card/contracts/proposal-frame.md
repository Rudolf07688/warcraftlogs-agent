# Contract: proposal frame, done-linking, reload

Design: `participants-and-confirmation.html#transport`. Shape: 029's `ProfileProposalOut`.

## Frame (server → client)

```json
{ "type": "proposal", "proposal": { "id": "…", "conversation_id": "…", "message_seq": null,
  "status": "pending", "created_at": "…", "expires_at": "…", "applied_at": null, "items": [ … ] } }
```

- Sent from `ws._handle_tool_end` when `name == "propose_profile_changes"` and `ok` (the runner sets
  `ok = result.status == "success"`), after the `tool_end` frame and before `done`.
- The id comes from `result["proposal"]["id"]`. The payload is `get_proposal(identity, id)` (the stored
  row, its own transaction), never the tool result.
- A missing or invalid id, or a `ProposalError` (e.g. another tenant's id): no frame,
  `logger.warning`.
- `_handle_tool_end` returns the sent id (or `None`). Older clients ignore the unknown frame type.

## Linking at done

- After `repo.add_message(... "agent" ...)` and `repo.assign_message_seq_to_turn_captures(...)`, in
  the same session: `set_message_seq(session, turn_proposal_ids, agent_msg.seq, tenant_id, user_id)`.
- Turns that end in an error or a disconnect never reach it, so their proposals keep
  `message_seq = null`.

## Reload

- `GET /api/conversations/{id}` gains `proposals: ProfileProposalOut[]`, from
  `profile_proposals.list_proposals(identity, conv_id)` (oldest first, status computed).
- `restClient.getConversation` attaches each proposal with a `message_seq` to the message with that
  `seq` (`message.proposals`), like artifacts. `detail.proposals` keeps the full list, and the App
  renders the unlinked ones as standalone cards.
