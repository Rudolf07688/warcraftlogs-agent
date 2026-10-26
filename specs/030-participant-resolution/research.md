# Research: Participant Resolution

## R1 Source of participants
Decision: `playerDetails` plus report region in one `_report_fields` call. Rationale: only it carries spec and role; `masterData` has no spec/role and is large; report summary has no role. Alternatives: slim `get_report_player_details` (breaks gear/talent use); flag on it (two output shapes).

## R2 Parsing
Decision: pure `participants_from_player_details`. `datasheet._player_details` flattens the same groups but drops the group name; it is kept as is (different output, role not needed there). Not a third copy, so no extraction now. Class validity via `roster_snapshot()` drops pets and NPCs.

## R3 Spec and role
Decision: most-played spec by `count`; role from the roster for that spec, else first group seen. Per clarify Q2.

## R4 Unknown realm
Decision: keep row, realm null (Q1, D12 correction); 029 validation flags it.

## R5 Run candidates
Decision: preamble lines from `recent_raids` / `recent_mplus_runs` / `tracked_raids`; no list-runs tool (would need DB inside `wcl_agent`).

## R6 Testing ambiguity
Decision: deterministic (preamble content + prompt-contract clause); see plan.

## R7 Fixtures
Decision: Inferred shapes from repo; no live call (Q5). Open: exact `server`/`type` formats checked live at review.
