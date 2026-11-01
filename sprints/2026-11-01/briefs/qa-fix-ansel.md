# QA fix: Ansel (seat dev-1), worktree /home/rudolf/dev/wcl-worktrees/dev-a, branch qa-fix-ansel

Read `qa-fix-common.md` first.

## Findings to fix
1. **BUG-001 (High)** ability-filtered tables are chunked as full-metric tables (`backend/app/kb/wcl_chunker.py:274-375`). A fetch with `abilityID` set must never pass for or dedup against the full table. Your choice: skip it (`chunkable_query`/`chunk_fetch` return nothing) or give it its own chunk_key/label/`extra["ability_id"]`. Skipping is fine and simplest.
2. **BUG-004 (Medium)** `backend/app/kb/guide_chunker.py:48-60,81`: a heading of about 1,940+ chars makes the section split loop forever on the event loop. Cap the title in `head`, clamp `room`, and guarantee the loop always advances.
3. **Spec drift (Low, operator-facing)**: migration 0019's docstring and error message, and `specs/043-kb-store-embed/research.md`, still name the rejected `pgvector/pgvector:pg17` tag; they must say `pgvector/pgvector:pg17-trixie` (board #82). Editing the message string in 0019 is fine (not deployed yet); don't change the schema.
4. **Doc claim (Medium in spec report, BUG-003)**: `config.py`, `indexer.py`, `main.py` and `documentation/ai_guide.md` say a dropped indexer job is "recovered by the backfill". It isn't for sources that already have chunks. Don't build the recovery (it's backlog `kb-backfill-hardening`); make the comments/docs say what is true: a dropped job of an already-indexed source stays stale until the source changes again or the follow-up lands.

## Footprint
backend/app/kb/wcl_chunker.py, backend/app/kb/guide_chunker.py, backend/app/kb/indexer.py (comment only), backend/app/config.py (comment only), backend/app/main.py (comment only), backend/migrations/versions/0019_*.py (docstring/message only), documentation/ai_guide.md, specs/043-kb-store-embed/research.md, and tests for these.
