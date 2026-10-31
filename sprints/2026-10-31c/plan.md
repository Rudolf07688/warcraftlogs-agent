# Sprint 2026-10-31c plan (Maren, PO)

Goal: start epic 103 (local-first data) and fix the live-pass tool_start flood plus five small fixes. 19 pts. Full plan: `plan.html`.

| Feature | Dev | Tier · model | Stories | Pts |
|---|---|---|---|---|
| 039 local-first data | Ansel (dev-1) | M · opus/high | sc-178 → sc-177 → sc-129 | 10 |
| 040 small fixes | Tomas (dev-2) | S · sonnet/high | sc-289, sc-213, sc-268, sc-272, sc-276, sc-140 | 9 |

- Migration 0018 (down_revision 0017_proposal_user_rls) belongs to 039.
- sc-141 and sc-143 were dropped: the code has no Raids page or dropdown, and the analyze-in-new-chat button already exists (board #4). They were replaced by sc-140 and sc-276.
- Owner conditions for 039: a design note before code, a bypass attempt at hand-off and at merge, and drop sc-129 if sc-178 runs long.
- Drop order if needed: sc-129, then sc-140, then sc-213.
