# Checkpoint: 074

- Decisions (board `scope:074:*`): new-account = state; prompt lifecycle; selector rules;
  login redirect; storage on `tenants` columns.
- sc-514 done first in c5b72f4 (ProfileChangeIn docstring → comment; budget 12_800 → 12_733).
- Files: see plan.md "Source Code". `profile_service.py` untouched by design.
- Implementation starts at T001 (models) → T002 migration (proven on pg.py) → T003-T005 → tests.
