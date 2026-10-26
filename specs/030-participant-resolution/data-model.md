# Data Model: Participant Resolution

No stored entities change. Transient shapes only.

**Participant** (tool row, at most 120 chars of JSON): `name`, `realm` (null if absent), `region`, `class`, `spec`, `role` (`tank`|`healer`|`dps`).

**Result**: `{status, report_code, fight_id, region, participants[], provenance, completeness}`; error: `{status:"error", error_message}`.

**Run candidate** (preamble text only): M+: `dungeon +level, date, timed|depleted (report code, fight id)`; raid: `zone, difficulty, date (report code)`. At most 5 per kind, newest first.
