# Quickstart: Grounded, Patch-Aware Class Guides (feature 015)

How to run, verify and demo the feature. Commands run from the repo root.

## 0. Prerequisites

- `docker compose up -d postgres redis` (Redis from feature 014; the feature works without
  it but caches nothing).
- `.env`: WCL credentials, Gemini/Vertex credentials. New optional settings
  (`backend/app/config.py`): `WCL_GUIDE_REVIEW_MODEL`, `WCL_GUIDE_MAX_REVIEW_ROUNDS`,
  `WCL_GUIDE_BRIEF_MAX_CHARS`, `WCL_GUIDE_PREAMBLE_BRIEFS_MAX_CHARS`,
  `WCL_GUIDE_DATASHEET_MIN_SAMPLE`, `WCL_GUIDE_INUSE_DAYS`, `WCL_GUIDE_REPORT_PER_MINUTE`.
- `uv run --directory backend alembic upgrade head` → applies `0011_guide_content_types`.
- Before enabling `WCL_GUIDE_RESEARCH_FETCH_ENABLED=true` (fetching third-party guide pages)
  or `WCL_GUIDE_TALENT_NAMES_URL`, the maintainer reviews those sites' terms (research R5/R14).
  With both off, research uses search-grounded snippets plus Blizzard pages, and talent names
  come from cited sources.

## 1. Baseline FIRST (Story 4, FR-024)

Before merging any other story:

```bash
uv run python -m backend.evals.guides run --baseline
```

Commit `backend/evals/guides/reports/baseline.json`. Expect the gate to **fail** today
(that is the point of the baseline).

## 2. Unit and contract tests

```bash
uv run --extra test pytest -q
uv run --extra test pytest -q backend/tests/test_guide_pipeline_checks.py \
  backend/tests/test_coaching_brief.py backend/tests/test_roster.py \
  backend/tests/test_content_type.py backend/tests/test_guides_api_v2.py \
  backend/tests/test_prompt_contract.py backend/tests/test_profile_context.py
cd frontend && npm run build && npm run lint
```

## 3. Story checks

| Story | Check |
|---|---|
| 1 Date & patch | Freeze the clock in `test_prompt_contract` (two calls → two times). Live: start backend, wait > 24 h or set the clock, ask "what's today's date?" — matches. Generate a guide: header + `game_patch` equal `GET` zone partition. With WCL zones unreachable, generate → `failed`, reason `patch_unknown`. |
| 2 Brief | Chat about a raid log for a profile character with a ready Raid brief: the turn log shows the brief inlined whole; ask about a +12 → agent calls `get_coaching_brief(..., "mplus")` or says no verified Mythic+ guidance. |
| 3 Roster | `GET /api/guides` → `roster_source: "game_data"`, Demon Hunter has Havoc, Vengeance, Devourer. Stop WCL access → `fallback` with Devourer still listed. |
| 4 Accuracy | `uv run python -m backend.evals.guides run` → report + gate verdict, deltas vs baseline. |
| 5 Raid/M+ UI | Profile → Class Guides: switch to Mythic+, generate one spec's M+ guide only; Raid row stays "Not generated", dot shows status; viewer tabs; repeat at 360 px and keyboard only; time SC-014. |
| 6 Data sheet | `uv run python -m backend.evals.guides datasheet Mage/Fire raid` prints the sheet (sample size, abilities, min gaps); compare 3 abilities with WCL by hand. |
| 7 Checks | `pytest backend/tests/test_guide_pipeline_checks.py` (one fixture per defect). |
| 8 Research | Generate with a fixture search result containing a PTR page and a Classic page (unit test) → both in `fact_sheet.dropped`, none cited. |
| 9 Review | Seeded-error draft fixture (wrong CD, removed talent, unsupported claim, raid tip in M+) → each fixed/removed; unfixable → `needs_review`, viewer shows draft warning or last verified guide. |
| 10 Freshness | Set a row's `game_patch` to an older value, open the library → `stale_reason=patch_changed`; in-use row regenerates, other row regenerates when opened. Submit "Report an inaccuracy" → admin `GET /api/admin/guide-reports` shows it; after regeneration status `fixed`/`rejected`. |

## 4. Rollout order (Constitution II)

1. Accuracy check + baseline (Story 4) — no behaviour change.
2. Live time provider + briefing + dedicated author (Story 1) — still one content type.
3. Roster from game data + Devourer (Story 3).
4. Migration 0011 + content types + brief rendering + preamble/tool (Stories 2, 5 backend).
5. UI (Story 5 frontend).
6. Data sheet (6) → checks (7) → research filters (8) → review loop (9) → freshness/reports (10).
Re-run the accuracy check after each step; the gate must pass before step 6 ends.
