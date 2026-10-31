# Implementation Plan: Suggestions, titles, reports and class guides on the active LLM provider

**Branch**: `035-provider-generation-callsites` | **Date**: 2026-10-31 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/035-provider-generation-callsites/spec.md`
(signed off 2026-10-31), sprint plan section 035, provider contract
`sprints/2026-10-31/briefs/032-provider-layer-contract.md`.

## Summary

Add `wcl_agent/llm/generation.py`, the provider layer's text-generation side: `generate_text`
(prompt, model role, max tokens, temperature, thinking flag, retry policy), `generate_json` and
`generate_grounded`. It picks the Claude client (Anthropic API or Vertex, from `provider`) or the
genai client by model family and runs every call under the shared `generate_with_retry` loop.
Suggestions, titles and report synthesis call `generate_text`; the guide pipeline's
`generate_structured` / `generate_grounded` keep their signatures, validation, retry rule and
`GuideModelError`, and delegate the SDK calls. On Claude, structured output uses
`output_config.format` and research uses the server-side web search tool plus web fetch restricted
to the existing fetch domains. Vertex request shapes stay as they are. Tests run on fakes only;
this feature also owns the sprint-level end-to-end test and grep check.

## Technical Context

**Language/Version**: Python 3.14 (backend + `wcl_agent`)

**Primary Dependencies**: `anthropic` 1.11.0 (`AsyncAnthropic`, `transform_schema`, server tools),
`google-genai` 2.25.0, 032's `wcl_agent/llm/provider.py`, 011's `model_retry.generate_with_retry`.
No new dependency.

**Storage**: N/A (the guide research cache is unchanged)

**Testing**: pytest (+ pytest-asyncio); `httpx2.MockTransport` behind the real `AsyncAnthropic`
for Claude; object fakes for genai

**Target Platform**: Linux server (FastAPI app, compose)

**Project Type**: web service (backend only; no frontend change)

**Performance Goals**: unchanged bounds: suggestions 4 s, titles 15 s, reports 60 s; reports no
longer hold a worker thread

**Constraints**: no live calls in tests; no secret in errors or logs (032's client raises a
key-free `LlmProviderNotConfigured`); never send `temperature` or forced `tool_choice` to Claude;
`provider.py`, `config.py`, `main.py`, `model_retry.py` are read-only for 035

**Scale/Scope**: 4 call-site modules, 1 new module (~220 lines), 3 new test files, 5 adjusted test
files, README lines

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. DRY & reuse | Pass | One entry point replaces three hand-rolled genai calls and two per-module client caches; reuses `generate_with_retry`, `RetryPolicy`, `role_model`, `is_anthropic_model`, `fetchable_domains`, the provider's client builders. Gemini `grounding_sources` moves, not copies. |
| II. Step-wise | Pass | Slices: (1) `generate_text` + the three sc-252 sites, (2) `generate_json` + `generate_structured`, (3) `generate_grounded` + research seam, (4) e2e/grep + README. Each ends with its tests green. |
| III. Simplicity | Pass | Plain async functions, no class hierarchy or adapter registry; model-family `if` in one module. No new setting. |
| IV. Typed contracts | Pass | `Grounded` dataclass; existing Pydantic step schemas are the validation contract on both providers; typed signatures. |
| V. Async backend | Pass | Reports switch from a blocking call in a thread to the async client; all calls `await`ed under timeouts. |
| VI. GitNexus | Pass | Impact run on the worktree index (below); HIGH/CRITICAL items reported to the scrum master before editing. |
| VII. shadcn | N/A | No UI. |
| VIII. Backlog sync | Pass | sc-252/sc-253 In Progress; no `todo.md` change. |

Post-design re-check: unchanged (no violations; Complexity Tracking empty).

### GitNexus impact (worktree index at 3232321, upstream)

| Symbol | Risk | Direct callers | Note |
|---|---|---|---|
| `suggestions.generate_followups` | LOW | `api/ws.py::_send_suggestions` | signature unchanged |
| `conversation_titles.generate_title` | LOW | `retitle_conversation` | signature unchanged |
| `report_synthesis.synthesize_findings` | LOW | `api/reports.py::_synthesize_and_render` | signature unchanged; `_generate` removed (tests only) |
| `guide_pipeline.llm.generate_structured` | **CRITICAL** (5 processes) | `authoring.author_claims`, `authoring.revise_claims`, `research.collect_evidence_basic`, `review.review_claims` | signature, validation and errors unchanged; only the SDK call moves |
| `guide_pipeline.llm.generate_grounded` | LOW | `research.collect_evidence_basic` | `url_context: bool` → `fetch_domains`; the one caller and two test fakes updated |
| `guide_pipeline.llm.grounding_sources` | LOW | `generate_grounded` | moves to `generation.py` |
| `model_retry.generate_with_retry` | **CRITICAL** | `generate_title`, `llm._generate`, `generate_with_fallback` | not edited; gains callers in `generation.py` |
| `vertex.genai_client` (forwarder) | **CRITICAL** | `llm._get_client`, `report_synthesis._generate`, `suggestions._get_client`, `models._make_gemini_client` | 035 removes three callers; the forwarder is deleted only if 033 merged first and `models.py` no longer uses it |
| `_get_client` (two modules) | UNKNOWN (ambiguous name) | text search: `suggestions.py`, `guide_pipeline/llm.py`, `test_conversation_titles.py` | both removed; the test moves to the new seam |

## Project Structure

### Documentation (this feature)

```text
specs/035-provider-generation-callsites/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R8
├── data-model.md
├── quickstart.md
├── contracts/
│   └── generation.md    # generation.py functions, types, call-site table
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
wcl_agent/llm/
├── generation.py                         # NEW: generate_text, generate_json, generate_grounded
└── vertex.py                             # delete genai_client forwarder (only if 033 merged first)
backend/app/
├── suggestions.py                        # generate_text(FAST, thinking off, 1 attempt)
└── services/
    ├── conversation_titles.py            # generate_text(FAST, temp 0.2, thinking off, _POLICY)
    ├── report_synthesis.py               # generate_text(REPORT, 1 attempt), no thread
    └── guide_pipeline/
        ├── llm.py                        # delegate to generate_json / generate_grounded
        └── research.py                   # one line: fetch_domains=fetchable_domains()
backend/tests/
├── test_llm_generation.py                # NEW: entry points on fake Anthropic + genai
├── test_guide_pipeline_llm.py            # NEW: structured/grounded both providers
├── test_provider_e2e.py                  # NEW: sprint e2e (vertex|anthropic) + grep check
├── test_suggestions.py                   # moved to the generation seam
├── test_conversation_titles.py           # moved to the generation seam
├── test_report_synthesis.py              # moved to the generation seam
├── test_guide_pipeline_run.py            # fake signature: fetch_domains
└── test_guide_reports.py                 # fake signature: fetch_domains
README.md                                 # lines in 032's provider section
```

**Structure Decision**: Existing layout. The new module sits beside `provider.py` in
`wcl_agent/llm/` because it is part of the provider layer (contract rule) and is used by backend
code; backend call sites import it like they import `model_retry`.

## Complexity Tracking

None.
