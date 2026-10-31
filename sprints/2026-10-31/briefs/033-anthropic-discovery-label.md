# Brief 033 — Model discovery on the Anthropic API, provider label, discovery log fix

- **Feature:** 033 · **Branch:** `033-anthropic-discovery-label` (set `GIT_BRANCH_NAME=033-anthropic-discovery-label` for `/speckit-specify`; spec dir `specs/033-anthropic-discovery-label/`)
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (track A). The scrum master resets it to the sprint tip (032 merged) before you start.
- **Base ref:** `sprint-2026-10-31` @ `e78e4a1` (032 + 034 merged)
- **Stories:** sc-250 (3) model discovery, catalog and 429 sibling fallback on the Anthropic API; sc-251 (1) model picker shows which LLM provider is live; sc-159 (1, `qa-deferred`) QA SPEC-002/004: startup log line and empty-catalog handling. Move them to **In Progress** when you start.
- **Peer:** track B developer (`dev-b-034` or `dev-b-035`; the scrum master tells you).
- **Sprint files:** plan `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/plan.md` (section 033, overlap table), decisions `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/decisions.md` (D1–D5, D9, D10), ownership `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/ownership.md`.
- **Provider layer (032, merged):** `wcl_agent/llm/provider.py` and `specs/032-llm-provider-switch/contracts/provider-layer.md`. 032 added an interim static-discovery path under `anthropic` via config properties; you replace it with real discovery.
- **Load the `claude-api` skill** (Models API, model ids, 429/529 + retry-after).
- **No owner gate** (OWNER GO given, D10). Scrum-master gates only. **Drop order if late:** sc-159 first, then sc-251.

## Acceptance criteria (verbatim from plan.md)

1. *(sc-250)* With `anthropic`, catalog mode lists the Anthropic Models API, sorts API
   ids and aliases into the haiku/sonnet/opus classes (`WCL_ANTHROPIC_CLASSES`), probes
   each with the tool-carrying one-token call and keeps the newest `count` per class
   that answer. No Gemini models are offered. Static mode probes `WCL_ANTHROPIC_MODELS`
   in API form and is the fallback if listing fails.
2. *(sc-250)* The cached catalog key includes the provider. A Vertex catalog is never
   served under `anthropic`, or the reverse, and cached ids are validated in the active
   provider's id shape.
3. *(sc-250)* On a 429 or 529 from the Anthropic API, the turn retries (honouring
   `retry-after`), then switches to the same-class sibling. When both are busy it shows
   the same friendly message as on Vertex.
4. *(sc-251)* `GET /api/models` also returns `provider` (additive field). The picker
   shows a small read-only "Vertex AI" / "Anthropic API" label (shadcn via the MCP where
   one fits), readable at 390px, and never shows a key, project id or secret.
5. *(sc-159)* The specified model-discovery startup log line is emitted (feature 016
   spec), and a listing response with no models is treated as a listing failure (so
   the fallback runs), not as an empty catalog. This applies to both providers.
6. `vertex` behaviour is otherwise unchanged and the existing discovery tests pass.
   New tests use fakes: paged listing, API id classification, not-enabled and no-quota
   probes, the cache-key split, 429 → sibling, the response field, the label, and both
   sc-159 cases. Frontend build, typecheck and tests pass.

## Footprint (tentative; becomes the grant after /speckit-plan)

`wcl_agent/llm/models.py`, `wcl_agent/llm/model_retry.py` (sibling path for API ids),
`backend/app/main.py::_load_models`, the `wcl_agent/cache` model-catalog key,
`backend/app/config.py` (discovery settings only; replace 032's interim static path),
`wcl_agent/llm/provider.py` (a listing function, by grant) and `wcl_agent/llm/vertex.py`
(deleting the `anthropic_client` forwarder; also `genai_client` if 033 merges after 035), `backend/app/schemas.py::ModelsResponse`,
`backend/app/api/models.py`, the frontend model picker component and `frontend/src/api/restClient.ts`,
`frontend/src/types.ts` if needed, README/.env.example lines, tests, `specs/033-anthropic-discovery-label/**`.
**Not yours:** `frontend/src/App.tsx` (034; ask if you need it), `generation.py` and the 035 call sites.

## Working rules

- Ports: app **18033**, Postgres **15433**, Redis **16333**. Own `docker run` containers only.
- Never read the owner's `.env`; no live LLM calls. Fakes only.
- Run `node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs analyze --force` in your worktree first.
- shadcn MCP: pass `registries: ["@shadcn"]` explicitly; run the audit checklist after any add.
- Sub-agents: send the split (tasks → exact files → model/effort) to the scrum master first.
- No scope creep. Extras go to the scrum master as Backlog suggestions.
- Reply "ACK <thing>" to each grant/decision. Never push. Restore `CLAUDE.md` and `.specify/feature.json` before each commit.
