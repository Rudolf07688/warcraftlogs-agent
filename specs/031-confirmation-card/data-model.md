# Data model: 031

No new tables or columns. The proposal is 029's (`profile_proposals`, migration 0016;
`ProfileProposalOut` in `backend/app/schemas.py`, defined once by
`capabilities-and-tools.html#proposal-contract`).

## Backend (new Pydantic models in `backend/app/schemas.py`)

```python
class ProposalFrame(BaseModel):
    """Server → client, inside a turn after a successful propose_profile_changes (031)."""
    type: Literal["proposal"] = "proposal"
    proposal: ProfileProposalOut

class ProposalDecisionOut(BaseModel):
    """POST /api/profile/proposals/{id}/approve|cancel."""
    proposal: ProfileProposalOut
    follow_up: MessageOut | None = None   # the saved line; null on a repeat

class ConversationDetail(ConversationOut):        # existing
    messages: list[MessageOut] = []
    artifacts: list["ArtifactOut"] = []
    proposals: list["ProfileProposalOut"] = []    # NEW: list_proposals(identity, conv_id)
```

## Frontend mirror (`frontend/src/types.ts`)

Field names are exactly 029's.

```ts
export type ProposalStatus = "pending" | "applied" | "cancelled" | "expired";
export interface ProposalValidation { ok: boolean; code: string | null; message: string | null }
export interface ProposalItemResult {
  status: "applied" | "skipped" | "failed"; code: string | null; character_id: string | null;
}
export interface ProposalItem {
  index: number;
  action: "add" | "update" | "remove";
  target: "own" | "friend";
  name: string; realm: string; region: string;
  class_name: string | null; spec: string | null;
  raid_role: RaidRole | null; played_role: RaidRole | null; previous_raid_role: RaidRole | null;
  character_id: string | null;
  validation: ProposalValidation;
  result: ProposalItemResult | null;
}
export interface ProfileProposal {
  id: string; conversation_id: string; message_seq: number | null;
  status: ProposalStatus; created_at: string; expires_at: string; applied_at: string | null;
  items: ProposalItem[];
}
export interface ProposalDecision { proposal: ProfileProposal; follow_up: Message | null }
// Message gains: proposals?: ProfileProposal[]
// ConversationDetail gains: proposals?: ProfileProposal[]
```

`RaidRole` already exists in `types.ts` (`"tank" | "healer" | "dps"`).

## Card state (derived, not stored)

| Shown state | Condition |
|---|---|
| pending | `status === "pending"` and `now < expires_at` |
| expired | `status === "expired"`, or `status === "pending"` and `now ≥ expires_at` |
| applied / cancelled | `status` |

Row label: `result` when it isn't null (applied → "Added"/"Removed"/"Role set"; skipped → "Skipped ·
label"; failed → "Failed · label"). Otherwise the validation label (ok → action badge; not ok →
"Skipped · label"). `N = items.filter(i => i.validation.ok).length`.

## Profile-changed event (`frontend/src/lib/profileEvents.ts`)

```ts
export interface ProfileChange { proposal: ProfileProposal; targets: ("friend" | "own")[] }
```

Posted on `BroadcastChannel("wcl-profile")` and as a same-tab `CustomEvent("wcl-profile-changed")`.
`targets` = the distinct `target`s of the items whose `result.status === "applied"`.
