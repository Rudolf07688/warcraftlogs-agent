# Checkpoint: 035 (resume point for a fresh context)

**Developer**: dev-b-035 · **Scrum master**: scrum-master · **Peer**: dev-a-032 (track A)
**Worktree**: `/home/rudolf/dev/wcl-worktrees/dev-b` · **Branch**: `035-provider-generation-callsites`
(base: sprint tip 5883f97) · **Stories**: sc-252, sc-253 (In Progress; leave there until told)

## State (2026-10-31)

- Spec signed off (Clarifications Q1–Q5 encoded), plan + research R1–R8 + contracts/generation.md
  + data-model.md + quickstart.md + tasks.md (T001–T025) committed on the branch.
- Ownership grant: requested with the exact file list (plan.md "Source Code"); check the ledger
  `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-31/ownership.md` for status `granted`.
- **Implementation is blocked** until the scrum master sends "032 MERGED, rebase". Start at T001.

## Decisions (binding)

- Model-family dispatch in `wcl_agent/llm/generation.py` (`is_anthropic_model`); `active_provider()`
  only for server-tool variants. Only `provider.py` + `generation.py` may call it.
- Thinking-off on Claude: Haiku → `thinking: disabled`; other Claude → no thinking + effort `low`.
- Retry policies: suggestions 1 attempt, reports 1 attempt, titles existing 2-attempt `_POLICY`.
- Claude research: ≥1 search error block and 0 results → `GuideModelError`; no searches / empty
  successful searches continue. Gemini unchanged.
- `llm.generate_grounded(model, prompt, *, fetch_domains)` replaces `url_context`; research passes
  `fetchable_domains()`; Claude web fetch `allowed_domains` = that list.
- Tools: `web_search_20260209` (max_uses 10), `web_fetch_20260209` (max_uses 5) on the Anthropic
  API; `web_search_20250305`, no fetch, for Claude on Vertex. `pause_turn` ≤ 3 resumes.
- Structured: `output_config.format` json_schema via `anthropic.transform_schema`, validated by our
  `model_validate_json`; `max_tokens` 16 000 for guide calls.
- Never send `temperature` or forced `tool_choice` to Claude.
- "not enabled" 400 → `ServerToolDisabled` → `GuideModelError` naming
  https://platform.claude.com/settings/capabilities.
- 035 owns the sprint e2e test + grep check (`backend/tests/test_provider_e2e.py`).
- `vertex.genai_client` forwarder: delete only if 033 merged first and `models.py` no longer uses it.

## Files owned (pending grant)

See plan.md "Source Code". Not ours: `provider.py`, `config.py`, `main.py`, `model_retry.py`,
`models.py`, `CLAUDE.md`, `.specify/feature.json` (restore both before each commit).

## Open questions

None. GitNexus CRITICAL items (generate_structured, generate_with_retry, genai_client forwarder)
reported to the scrum master with mitigations in plan.md.
