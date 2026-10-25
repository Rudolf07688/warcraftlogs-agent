# File ownership ledger — sprint 2026-10-25

Single source of truth for who may edit what (scrum-master role §2). A path is granted
to at most one owner at a time. Status: tentative (from brief footprint) → granted
(after `/speckit-plan` file list) → released (feature merged).

Sprint branch: `sprint-2026-10-25` (base `4923785`). Worktrees: track A
`/home/rudolf/dev/wcl-worktrees/dev-a`, track B `/home/rudolf/dev/wcl-worktrees/dev-b`.

## Standing ownership

| Path or glob | Owner | Feature | Status | Since |
|---|---|---|---|---|
| `CLAUDE.md` | scrum-master | — | granted | 2026-10-25 |
| `AGENTS.md` | scrum-master | — | granted | 2026-10-25 |
| `todo.md` | scrum-master | — | granted | 2026-10-25 |
| `.specify/memory/constitution.md` | scrum-master | — | granted | 2026-10-25 |
| `.specify/feature.json` | scrum-master | — | granted | 2026-10-25 |
| `sprints/2026-10-25/ownership.md`, `log.md`, `briefs/**` | scrum-master | — | granted | 2026-10-25 |
| `sprints/2026-10-25/plan.md`, `decisions.md` | product-owner | — | granted | 2026-10-25 |
| `pyproject.toml`, `uv.lock` | (one dev at a time; ask) | — | unassigned | 2026-10-25 |
| `frontend/package.json`, `frontend/package-lock.json` | (one dev at a time; ask) | — | unassigned | 2026-10-25 |
| new `backend/migrations/versions/*` | (scrum master assigns revision; next is `0012_*`, down_revision `"0011_guide_content_types"`) | — | unassigned | 2026-10-25 |

## Feature grants

| Path or glob | Owner | Feature | Status | Since |
|---|---|---|---|---|
| `wcl_agent/**` (22 git mv, 6 new `__init__.py`, edits in all 25 modules) | dev-a-018 | 018 | released (merged 36bce56) | 2026-10-25 |
| `backend/app/{agent_runner,config,main,model_state,schemas,suggestions}.py`, `backend/app/api/{cache_stats,guides,reports,ws}.py`, `backend/app/services/{guide,profile_context,raids,recent_raids,report_synthesis}.py`, `backend/app/services/guide_pipeline/{briefing,checks,datasheet,llm,research}.py`, `backend/evals/guides/{__main__,adversarial,coaching,scoring}.py` (reference lines only) | dev-a-018 | 018 | released (merged 36bce56) | 2026-10-25 |
| `backend/tests/{conftest,wcl_fakes}.py` and `backend/tests/test_{artifacts,benchmark,cache_families,cache_stats,charts,coaching_brief,context_injection,context_trim,cooldowns,eval_scoring,fight_time,genai_compat,greeting,guide_meta,guide_pipeline_briefing,guide_pipeline_datasheet,guides_and_boot,guides_tool,message_report,model_discovery,model_retry,models,profile_context,profile,provenance,recent_raids,report_rankings,report_synthesis,roles,roster,runner_retry,spec_guides,stale_scan,tenant_isolation,tool_concurrency,vertex,wcl_async,wcl_cache,wcl_loop_lag,ws_rate_limit}.py` (42 files, reference lines only) | dev-a-018 | 018 | released (merged 36bce56) | 2026-10-25 |
| `README.md`, `documentation/ai_guide.md`, `documentation/live_model_probe.md` | dev-a-018 | 018 | released (merged 36bce56) | 2026-10-25 |
| `frontend/src/lib/classColors.ts` (line-2 comment only) | dev-a-018 | 018 | released (merged 36bce56) | 2026-10-25 |
| `specs/018-wcl-agent-subpackages/**` | dev-a-018 | 018 | released (merged 36bce56) | 2026-10-25 |
| `main.py`, `backend/tests/test_{grounding,prompt_contract,startup}.py`, `pyproject.toml`/`uv.lock` token | (was dev-a-018) | 018 | released (no edit needed) | 2026-10-25 |
| `backend/migrations/versions/0012_conversation_pin_title.py` (down_revision `0011_guide_content_types`) | dev-b-019-v2 | 019 | released (merged 8fa7506) | 2026-10-25 |
| `backend/app/db/repository.py`, `backend/app/api/conversations.py` | dev-b-019-v2 | 019 | released (merged 8fa7506) | 2026-10-25 |
| `backend/app/db/models.py` (Conversation columns, done in dad5f8c) | dev-b-019-v2 | 019 | released (declared final; transferred to 020) | 2026-10-25 |
| `backend/tests/test_conversation_pinning.py`, `backend/tests/test_conversation_migration.py`, `backend/tests/test_conversation_titles.py` (new) | dev-b-019-v2 | 019 | released (merged 8fa7506) | 2026-10-25 |
| `frontend/src/components/Sidebar.tsx`, `frontend/src/App.tsx`, `frontend/src/types.ts`, `frontend/src/api/restClient.ts`, `frontend/src/api/wsClient.ts` | dev-b-019-v2 | 019 | released (merged 8fa7506) | 2026-10-25 |
| `backend/app/services/conversation_titles.py` (new) | dev-b-019-v2 | 019 | released (merged 8fa7506) | 2026-10-25 |
| `specs/019-sidebar-conversations/**` | dev-b-019-v2 | 019 | released (merged 8fa7506) | 2026-10-25 |
| `backend/app/schemas.py`, `backend/app/api/ws.py` (sc-155 hook), `backend/tests/conftest.py`, `documentation/ai_guide.md` (2 lines) | dev-b-019-v2 | 019 | released (merged 8fa7506) | 2026-10-25 |
| `wcl_agent/llm/models.py`, `wcl_agent/llm/model_retry.py`, `backend/app/model_state.py`, `backend/app/agent_runner.py`, `backend/app/api/ws.py` | dev-a-021 | 021 | released (merged 8fd3d53) | 2026-10-25 |
| `frontend/src/api/wsClient.ts`, `frontend/src/components/MessageList.tsx` (PO exception, decision 27), `frontend/src/toolLabels.ts`, `documentation/ai_guide.md` (1 line) | dev-a-021 | 021 | released (merged 8fd3d53) | 2026-10-25 |
| `backend/tests/test_model_fallback.py`, `test_model_fallback_ws.py`, `test_model_fallback_history.py` (new), `specs/021-ratelimit-fallback/**` | dev-a-021 | 021 | released (merged 8fd3d53) | 2026-10-25 |
| `backend/app/schemas.py`, `frontend/src/types.ts`, `frontend/src/App.tsx` | dev-a-021 | 021 | released (merged 8fd3d53) | 2026-10-25 |
| `wcl_agent/client/wcl_client.py`, `backend/app/config.py` (3 settings), `backend/app/main.py` (lifespan), `.env.example` | dev-a-020 | 020 | released (merged 3be583d) | 2026-10-25 |
| `backend/app/db/models.py` (append `RawFetch` at end only) | dev-a-020 | 020 | released (merged 3be583d) | 2026-10-25 |
| `documentation/ai_guide.md` (1–3 lines) | dev-a-020 | 020 | released (merged 3be583d) | 2026-10-25 |
| `backend/migrations/versions/0013_raw_fetches.py` (down_revision `0012_conversation_pin_title`), `backend/app/repositories/raw_fetches.py`, `backend/app/services/fetch_persistence.py`, `backend/tests/test_raw_fetch_{client,store,writer}.py`, `specs/020-fetch-persistence/**` | dev-a-020 | 020 | released (merged 3be583d) | 2026-10-25 |
| `wcl_agent/cache/**`, other `wcl_agent/client/**` | — | — | free (F5/022 needs wcl_client.py after 020 merges) | 2026-10-25 |
| migration slots | 0012 → 019 (merged), 0013 → 020 (merged), 0014 → 022 (merged) | — | assigned | 2026-10-25 |

## Withdrawn

| Path or glob | Owner | Feature | Status | Since |
|---|---|---|---|---|
| F4-security footprint (StreamMarkdown, nginx.conf, vite.config.ts, auth.py, auth_service.py, rate_limit.py, Dockerfile, docker-compose.yml, .env.example, auth tests) | dev-b-019 | 019-security (withdrawn) | released | 2026-10-25 |

Note: plan revision 2 (decision 8) took sc-157 and sc-158 out of the sprint. The
security brief moved to `briefs/withdrawn/`.
| `backend/app/services/recent_raids.py`, `backend/app/services/recent_raid_types.py`, `backend/app/api/recent_raids.py`, `backend/app/schemas.py`, `backend/app/db/repository.py` | dev-b-022 | 022 | released (merged 18a4656) | 2026-10-25 |
| `wcl_agent/client/queries.py`, `wcl_agent/cache/cache_models.py`, `wcl_agent/cache/cache.py` (report_summary key bump), `wcl_agent/tools/report_tools.py` (`_summary_from`) | dev-b-022 | 022 | released (merged 18a4656) | 2026-10-25 |
| `frontend/src/components/WelcomePanel.tsx`, `frontend/src/types.ts`, `frontend/src/api/restClient.ts`, `frontend/src/App.tsx` | dev-b-022 | 022 | released (merged 18a4656) | 2026-10-25 |
| `backend/migrations/versions/0014_recent_mplus_runs.py` (down_revision `0013_raw_fetches`), `backend/tests/test_recent_mplus.py` (new), `backend/tests/test_recent_raids.py`, `backend/tests/test_wcl_cache.py` + `test_cache_families.py` (only if pinning v1 key), `specs/022-welcome-mplus/**` | dev-b-022 | 022 | released (merged 18a4656) | 2026-10-25 |
| `backend/app/db/models.py` (append only), `backend/app/config.py` (2 settings) | dev-b-022 | 022 | released (merged 18a4656) | 2026-10-25 |
| `frontend/src/styles.css`, `frontend/src/index.css`, `specs/023-larger-font/**` | dev-b-023 | 023 | released (merged ea186a2) | 2026-10-25 |
| `frontend/src/components/Sidebar.tsx` (line 154, `text-[11px]` → `text-[0.6875rem]` only) | dev-b-023 | 023 | released (merged ea186a2) | 2026-10-25 |
| `backend/app/services/recent_raids.py`, `backend/app/services/recent_raid_types.py` (if needed), `backend/app/api/recent_raids.py` (if needed), `frontend/src/components/WelcomePanel.tsx`, `backend/tests/test_recent_mplus.py`, `specs/022-welcome-mplus/**` | dev-a-024 | 024 (QA fix X) | tentative | 2026-10-25 |
| `backend/migrations/versions/0012_conversation_pin_title.py`, `backend/tests/test_conversation_migration.py` (if needed), `README.md`, `documentation/ai_guide.md`, `specs/018-wcl-agent-subpackages/**`, `specs/019-sidebar-conversations/**`, `specs/023-larger-font/**` | dev-b-025 | 025 (QA fix Y) | tentative | 2026-10-25 |
