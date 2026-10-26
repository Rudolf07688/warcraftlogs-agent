# Contract: approve / cancel routes

Design: `participants-and-confirmation.html#transport` (REST table), `#followup`. Router
`backend/app/api/proposals.py`, prefix `/api/profile/proposals`, registered in `main.py`.

Dependencies: `require_csrf` (session + CSRF). The follow-up line is saved in a short
`tenant_scope` opened only for that write (research R2). The routes call **only** `profile_proposals.get_proposal`, `execute_proposal` and
`cancel_proposal`, and never touch `user_characters`.

| Route | 200 body (`ProposalDecisionOut`) | Errors (`detail`) |
|---|---|---|
| `POST /{id}/approve` | `{proposal (applied, per-item results), follow_up: MessageOut \| null}` | 404 `not_found` · 409 `proposal_expired` · 409 `proposal_cancelled` |
| `POST /{id}/cancel` | `{proposal (cancelled), follow_up: MessageOut \| null}` | 404 `not_found` · 409 `proposal_applied` · 409 `proposal_expired` |

- `ProposalError(code)` → 404 for `not_found`, else 409 with `detail=code`.
- `follow_up` is saved and returned only when this call moved the proposal from `pending` (read
  first with `get_proposal`). A repeat returns the stored state with `follow_up: null`.
- Cancel returning status `expired` → 409 `proposal_expired`.
- The follow-up is an agent message in `proposal.conversation_id`. It's never added to the ADK
  session (D10).

## Follow-up text (`follow_up_text(proposal)`, pure)

Labels (same as the card): duplicate_friend, already_friend → "already a friend"; already_own,
duplicate_character → "your own character"; character_limit → "character limit reached";
friend_limit → "friend limit (50) reached"; invalid_name → "name not valid"; invalid_realm →
"realm unknown, add by hand"; invalid_region → "region unknown"; invalid_item → "not valid";
duplicate_item → "listed twice"; not_found → "no longer in your profile"; no_change → "already set";
other → "not applied".

Examples:
- `Done. Added 3 friends: Kazrok, Brightmane and Velyra. Skipped 1: Nightpaw (already a friend).`
- `Done. Removed 1 friend: Nightpaw. Set Velyra's role to healer.`
- `Added 2 friends: Kazrok and Brightmane. Couldn't add Velyra (realm unknown, add by hand). Nothing else changed.`
- Cancel: `Cancelled. Your profile is unchanged.`
