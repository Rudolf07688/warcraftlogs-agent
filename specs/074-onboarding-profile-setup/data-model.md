# Data model: 074

## profile_settings (migration 0023_profile_main_spec, down_revision 0022_pg_stat_statements)

One row per tenant, created on the first save or skip. RLS as `profile_proposals`.

| column | type | notes |
|---|---|---|
| tenant_id | uuid PK, FK tenants ON DELETE CASCADE | from the session only |
| main_class | varchar(40) null | roster class filter value, e.g. `Paladin` |
| main_spec | varchar(40) null | one of `main_class`'s specs; null when class is null |
| main_content | varchar(8) null | CHECK `main_content IN ('raid','mplus','both')` (`ck_profile_settings_main_content`) |
| onboarding_dismissed_at | timestamptz null | set once by "Skip for now"; 0023 inserts `now()` rows for existing tenants |
| updated_at | timestamptz | server default now() |

Validation (app, not DB): class in roster; spec requires class and is one of its specs.
The roster can change, so spec/class membership is not a DB constraint.

## Derived: onboarding_pending
`(no row OR onboarding_dismissed_at IS NULL) AND NOT EXISTS (own character of the tenant)`.

State: pending → (skip) → dismissed (terminal). Pending → (own character added) → not pending
(returns to pending only if all own characters are removed and it was never skipped).
