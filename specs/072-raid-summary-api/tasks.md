# Tasks: 072 raid summary API

- [X] T001 Repository reads `read_visible_summary` and `read_visible_parts` in backend/app/repositories/raw_fetches.py
- [X] T002 Service + pydantic models in backend/app/services/raid_summary.py (keys, summary, participants, my characters, parses, caps)
- [X] T003 Route + `valid_report_code` dependency in backend/app/api/raids.py
- [X] T004 Contract test: seeded raid equals the contract shape (backend/tests/test_072_raid_summary.py)
- [X] T005 Key pinning: the keys equal what the tools send (fake client)
- [X] T006 No WCL call; has_data false with nothing stored; each part missing alone
- [X] T007 Hostile: other workspace's tracked code 404 + no leak; public untracked 404; grant-only for another tenant not used
- [X] T008 Hostile: path tricks 404 before the service runs; uploader text capped/cleaned; identity by name+realm+region from profile rows
- [X] T009 Postgres test of both reads (backend/tests/test_072_raid_summary_pg.py)
- [X] T010 mutate.py bite on the visibility guard of each new read
- [X] T012 Re-verify (decision:072-reverify): one summary request, in-band status + grant, timeout, cooldown; tests incl. Postgres RLS
- [X] T011 detect-changes, check.py receipt, contract "as built" post, hand-off
