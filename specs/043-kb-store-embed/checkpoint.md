# Checkpoint: 043 after Gate 2 (plan + tasks)

- Branch `043-kb-store-embed` from `sprint-2026-11-01`. Spec passed Gate 1 (#44).
- Decisions: board `clarify:043-*` #31–#35, schema for 044 #36, backlog `kb-dropped-jobs`.
  Contract 5 (#45): Tomas's `store_batch` returns `BatchResult(gone, changed: list[FetchedResponse])`;
  my hook consumes `changed` after the commit; I don't edit `upsert_raw_fetch`.
- Files per story: plan.md "Exact file list per story". Sequenced: `config.py`,
  `fetch_persistence.py`, `raw_fetches.py` (iterator only) after 045 part 1. Grants requested:
  `guide_pipeline/__init__.py`, `main.py`, `ws.py`, docs (`.env.example`, `README.md`, `ai_guide.md`).
- Implementation starts at tasks.md T001 (sc-111), Stop 3 after T010.
- Keep `.specify/feature.json` pointing at 043 during Spec Kit steps; restore before commits
  (and check no `specs/017` file is modified).
