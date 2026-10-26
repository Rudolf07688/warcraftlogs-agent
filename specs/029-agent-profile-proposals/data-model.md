# Data Model: Capability Summary and Profile Proposal Tools (029)

The single definition of the proposal shape is the design's
[`#proposal-contract`](../../documentation/designs/self-aware-agent/capabilities-and-tools.html#proposal-contract).
This file maps it onto code. It doesn't redefine it.

## Table `profile_proposals` (new, migration `0016_profile_proposals`)

Revision `"0016_profile_proposals"`, down_revision `"0015_rescan_mplus_runs"` (granted by the
scrum master). The columns follow design C9.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | uuid4, server-generated |
| tenant_id | UUID NOT NULL | FK tenants ON DELETE CASCADE |
| user_id | UUID NOT NULL | FK users ON DELETE CASCADE |
| conversation_id | UUID NOT NULL | FK conversations ON DELETE CASCADE |
| message_seq | INTEGER NULL | Set by 031 when the turn's answer is saved (artifact precedent) |
| status | VARCHAR(10) NOT NULL DEFAULT 'pending' | pending · applied · cancelled · expired |
| items | JSON NOT NULL | `list[ProposalItemOut]`, validated through Pydantic on read and write |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| expires_at | TIMESTAMPTZ NOT NULL | created_at + `PROPOSAL_TTL` (30 min) |
| applied_at | TIMESTAMPTZ NULL | |

- Index `ix_profile_proposals_tenant_conversation (tenant_id, conversation_id)`.
- Postgres only, as in 0014: `ENABLE` + `FORCE ROW LEVEL SECURITY`, policy `tenant_isolation`
  `USING/WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)`,
  and `GRANT SELECT, INSERT, UPDATE, DELETE` to the runtime role (`APP_DB_USER`, default
  `wcl_app`). The downgrade drops the policy, the index and the table.
- ORM: `ProfileProposal` in `backend/app/db/models.py`, using `_UUID`/`_JSON` like `Artifact`.

### State transitions

```
pending ──execute──▶ applied            (final)
pending ──cancel───▶ cancelled          (final)
pending ──now ≥ expires_at──▶ expired   (computed on every read; stored by execute and cancel)
```

Final states never change. On a pending row past `expires_at`, `get_proposal` and
`list_proposals` report `expired` and store nothing. `execute_proposal` and
`cancel_proposal` store `expired`.

## Pydantic models (`backend/app/schemas.py`, new)

| Model | Fields | Used by |
|---|---|---|
| `ProfileChangeIn` | action `Literal["add","update","remove"]`; target `Literal["own","friend"]`; name `str`; realm `str`; region `str`; class_name `str \| None`; spec `str \| None`; raid_role `RaidRole \| None`; played_role `RaidRole \| None`. No length constraints (research R1). | Tool argument, `create_proposal` |
| `ProposalValidation` | ok `bool`; code `ValidationCode \| None`; message `str \| None` | Item |
| `ProposalItemResult` | status `Literal["applied","skipped","failed"]`; code `str \| None`; character_id `UUID \| None` | Item |
| `ProposalItemOut` | index, action, target, name, realm, region, class_name, spec, raid_role, played_role, previous_raid_role, character_id, validation, result (null until executed) | Proposal |
| `ProfileProposalOut` | id, conversation_id, message_seq, status, created_at, expires_at, applied_at, items (1–30) | Tool result, every service function, 031 frames/routes |

`ValidationCode` = `Literal[...]` over the design's 13 codes (`#validation-codes`):
duplicate_character, duplicate_friend, already_friend, already_own, character_limit,
friend_limit, invalid_name, invalid_realm, invalid_region, duplicate_item, not_found,
no_change, invalid_item. `RaidRole` is the existing alias.

## Constants

| Name | Value | Where |
|---|---|---|
| `MAX_FRIENDS` | 50 | `backend/app/db/repository.py`, next to `MAX_OWN_CHARACTERS` (D8) |
| `MAX_PROPOSAL_ITEMS` | 30 | `backend/app/services/profile_proposals.py` (C13) |
| `PROPOSAL_TTL` | `timedelta(minutes=30)` | same (C10) |
| `CAPABILITY_SUMMARY_MAX_CHARS` | 4000 | `wcl_agent/capabilities.py` (C3) |
| `MAX_TOOL_LINE_CHARS` | 160 | same (C3) |

## Internal value objects (dataclasses)

- `ToolGroup(label: str, tools: tuple, note: str = "")`, frozen, in `wcl_agent/capabilities.py`.
- `CharacterNotFound(Exception)` in `backend/app/services/profile_service.py`.
- `ProposalError(Exception)` with `code` in `not_found`, `proposal_expired`,
  `proposal_cancelled`, `proposal_applied`, in `backend/app/services/profile_proposals.py`.

## Changed existing entity

- `user_characters` (no schema change). `repo.add_character` refuses a 51st friend with
  `CharacterConflict("friend_limit")`; existing rows are never trimmed.
  `repo.find_character_identity` compares
  `replace(replace(lower(trim(server)), ' ', '-'), '''', '')` with `server_slug(server)`.
  The name and region comparisons are unchanged.
