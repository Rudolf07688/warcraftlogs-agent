# Brief 035 — Suggestions, titles, reports and class guides on the active provider

- **Feature:** 035 · **Branch:** `035-provider-generation-callsites` (set `GIT_BRANCH_NAME=035-provider-generation-callsites` for `/speckit-specify`; spec dir `specs/035-provider-generation-callsites/`)
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (track B). The scrum master resets it to the sprint tip before you start.
- **Base ref:** `sprint-2026-10-31` @ `6e5cef7` (034 merged; 032 not yet — see Sequencing)
- **Stories:** sc-252 (2) follow-up suggestions, chat titles and report synthesis run on the active LLM provider; sc-253 (3) grounded class-guide pipeline runs on the Anthropic API (structured output and web search). Epic 248. Move them to **In Progress** when you start.
- **Peer:** track A developer (`dev-a-032` or `dev-a-033`; the scrum master tells you).
- **Sprint files:** plan `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/plan.md` (section 035, overlap table, sprint-level e2e), decisions `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/decisions.md` (D1–D5, D9, D10 binding), ownership `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/ownership.md`.
- **Provider-layer contract (032; specify against it, don't re-derive it):** `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/briefs/032-provider-layer-contract.md`. Once 032 merges, the authoritative copy is `specs/032-llm-provider-switch/contracts/provider-layer.md` on the sprint branch.
- **Load the `claude-api` skill** (web search tool, structured output, current model constraints: no temperature/top_p/top_k on current Claude models; no forced tool_choice on Opus/Sonnet 5.5 — use output_config.format).
- **No owner gate** (OWNER GO given, D10). Scrum-master gates only.

## Acceptance criteria (verbatim from plan.md)

1. *(sc-252)* One provider-neutral text-generation entry point (prompt, model role, max
   tokens, temperature) serves suggestions, titles and report synthesis on either
   provider, through the shared retry loop. No `google.genai` types or provider
   branches remain in those three modules.
2. *(sc-252)* With `anthropic`, suggestions and titles use the fast-role model and
   reports use the report-role model. Fail-closed behaviour is unchanged (no
   suggestions; the first-message title is kept; a clean 500 with no partial PDF), and
   the existing timeouts still hold.
3. *(sc-253)* `generate_structured` works on both providers: output is validated against
   the same Pydantic schema, with the same one-retry rule and `GuideModelError`.
4. *(sc-253)* `generate_grounded` works on both providers. Under `anthropic` it uses
   Anthropic's server-side web search tool and returns `GroundedText` with
   `{title, uri}` sources from the results. URL context maps to web fetch or is
   documented as unavailable, and `WCL_GUIDE_RESEARCH_FETCH_ENABLED` is never bypassed.
5. *(sc-253)* Under `anthropic`, guide author and reviewer default to two different
   Claude models, and the startup check that they differ still runs. If web search isn't
   enabled for the Anthropic organisation, research fails as a clear `GuideModelError`
   (the run is held as today), and README says how to enable it.
6. `vertex` behaviour is unchanged and the existing suggestion, title, report and
   guide-pipeline tests pass. New tests use faked Anthropic and genai clients (including
   web-search result blocks and a validation retry). No live calls.

## Decisions already made (don't reopen)

- The entry point lives in a NEW `wcl_agent/llm/generation.py`, owned by you and counted as part of
  the provider layer: it's the only module besides `provider.py` that may call `active_provider()`.
  Call sites never branch on the provider. The sprint grep check exempts `provider.py` + `generation.py`.
- Models per role come from 032's settings (`wcl_suggest_model`, `wcl_report_model`, `wcl_guide_model`,
  `wcl_guide_review_model`) or `role_model(ModelRole.X)`. D9 defaults: report + guide author
  claude-sonnet-5-5, guide review claude-opus-5-5, fast claude-haiku-5-5.
- 032 leaves transitional `vertex.genai_client` / `vertex.anthropic_client` forwarders; your call sites
  import from the provider layer instead. `models.py` (033) also uses `genai_client`, so whichever of
  033/035 merges **last** deletes the `genai_client` forwarder (vertex.py granted for that only).
- AC 1 lists "temperature" as an entry-point parameter; under `anthropic` it must not be sent to the
  current Claude models (claude-api skill). Accept and ignore it there, and say so in the spec.

## Sequencing

- Specify, clarify, plan and tasks can start as soon as you're spawned (against the contract snapshot).
- **Implementation waits for 032 to merge**; the scrum master tells you "032 MERGED, rebase".

## Footprint (tentative; becomes the grant after /speckit-plan)

`backend/app/suggestions.py`, `backend/app/services/conversation_titles.py`,
`backend/app/services/report_synthesis.py`, `backend/app/services/guide_pipeline/llm.py`
(`research.py` only if the sources shape needs it), NEW `wcl_agent/llm/generation.py`,
`wcl_agent/llm/vertex.py` (deleting the genai forwarder only, after 032 merges), README lines
(after 032's provider section), the matching tests, `specs/035-provider-generation-callsites/**`.
**Not yours:** `provider.py`, `config.py`, `models.py`, `main.py`, `model_retry.py` (call `generate_with_retry`, don't edit it).

## Working rules

- Ports for any throwaway app or DB: app **18035**, Postgres **15435**, Redis **16335**. Own `docker run` containers only.
- Never read the owner's `.env`; no live LLM/WCL calls (no `ANTHROPIC_API_KEY`, no ADC). Fakes only.
- Run `node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --force` in your worktree before impact analysis and change detection.
- Sub-agents: send the split (tasks → exact files → model/effort) to the scrum master first.
- No scope creep: sc-252 + sc-253 only (no chat web search — D3). Extras go to the scrum master as Backlog suggestions.
- Reply "ACK <thing>" to each grant/decision. Never push. Restore `CLAUDE.md` and `.specify/feature.json` before each commit.
