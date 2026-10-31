# Data model: Profile write-path hardening

No new tables or columns.

## profile_proposals (RLS, migration 0017_proposal_user_rls)

| | Before (0016) | After (0017) |
|---|---|---|
| Policy | `tenant_isolation` | `tenant_user_isolation` |
| USING / WITH CHECK | `tenant_id = app.tenant_id` | `tenant_id = app.tenant_id AND user_id = app.user_id` |

Both settings are read with `NULLIF(current_setting(…, true), '')::uuid`, so a missing setting
matches no row. Downgrade drops the new policy and recreates `tenant_isolation`.

## Proposal item (JSON in `items`)

- `class_name`: a roster class key (e.g. `DemonHunter`) or null.
- `spec`: the roster's spec display name (e.g. `Beast Mastery`) or null; never set without a class.
- `realm`: unchanged spelling; must pass the realm-form rule for the item to be valid.

## Locks

- Per-tenant transaction advisory lock around every character add and every approval.
