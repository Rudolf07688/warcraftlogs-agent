# Checkpoint: 044 kb-search (before implementation)

Gates: Gate 1 passed (#37, two changes folded in), Gate 2 passed (#54). Grants (#57):
`wcl_agent/agent.py` (the clause in `_INSTRUCTION_BODY` only), `backend/app/agent_runner.py`
(first in the sequence: register `KB_TOOLS`, commit, then post `released`).

## Decisions in force
- Ranking #25: N=40 per leg, k 8 (1–15), RRF per query then across queries, dedupe by source.
- Relaxation #26: `user_stated` makes soft filters hard; spec → class → encounter → dates;
  difficulty and character never relax; relaxed hits rank below.
- Cap #27: 400 chars per hit, 6,000 chars per result, `capped`.
- Scope #28: visibility via `fetch_visible_clause` (no freshness); fail closed outside a turn.
- Applicability #29: a filter narrows only kinds that carry it.
- #37: stand-in eval reports only; `record` command; `spec_pairs` for spec-only filters.
- #36 (Ansel): schema names; `name_key(str)` is the one key function.

## Files
See plan.md "exact file list per story". Nothing else.

## Where implementation starts
T002/T003: `backend/tests/test_name_resolver.py` then `backend/app/services/name_resolver.py`.
Stop 3 after T004 (resolver hand-off only). Then T005–T008 (pure search + tool), T013 early
(agent_runner registration, then release), T009+ after the sc-111 merge, T011+ after sc-295.
