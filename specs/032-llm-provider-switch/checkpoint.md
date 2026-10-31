# Checkpoint: 032 LLM provider switch (resume point)

**Date**: 2026-10-31 · **Developer**: dev-a-032 · **Scrum master**: scrum-master · **Peer**: dev-b-034
**Worktree**: `/home/rudolf/dev/wcl-worktrees/dev-a` · **Branch**: `032-llm-provider-switch` ·
**Base**: `b963463` (sprint branch `sprint-2026-10-31`) · **Story**: sc-249 (In Progress, iteration 254)

## State

- Spec signed off (D9). Plan, research, data model, contracts, quickstart and tasks written and
  committed on the branch (`0aaa025` spec, `8461e12` plan, then tasks/checkpoint).
- **Gates**: OWNER GO in (D10). Plan gate passed and files granted (scrum master, 2026-10-31). Contract open point decided (035 owns `wcl_agent/llm/generation.py`). Tasks gate passed.
- **Implemented** (T001–T032, commits 8a6d4f0, 0c1db73, 281a0d3, 20ada77 and the hand-off commit). Handed off to the scrum master; waiting for review / PO acceptance. sc-249 stays In Progress.
- Baseline suite at `b963463` in this worktree: 1171 passed, 6 skipped, 1 deselected (83 s).

## Decisions (binding)

- Q1/D9: anthropic defaults: chat/report/guide `claude-sonnet-5-5`, guide review
  `claude-opus-5-5`, fast + greeting `claude-haiku-5-5`. Vertex defaults unchanged.
- Q2: explicit role value wins only if the active provider serves it; else one warning per role
  and the provider default.
- Q3: in scope, only in `agent.py` and `model_retry.py`: adaptive thinking for Claude ids
  (`thinking_budget=-1`), and `drop_block` + `anthropic-beta: thinking-binding-controls-2026-08-01`
  on adaptive Claude requests. Two fake-client tests (thinking config; drop_block + header). It
  restores Claude on Vertex; the hand-off must say so. No other thinking/prompt changes.
- Q4: stale model fallback on WS turns only; REST keeps its 400.
- Q5: new `WCL_GREETING_MODEL`; `backend/app/greeting.py` tentatively granted.
- PO (D9): prove the browser never sends an unserved model id, with a new test file only
  (`frontend/src/App.modelFallback.test.tsx`); `App.tsx` is 034's and stays untouched.
- SM condition: interim static discovery under `anthropic` must not edit `wcl_agent/llm/models.py`
  or `main.py::_load_models` (033 owns them). Done via Settings properties + provider module +
  the `vertex.anthropic_client` forwarder.

## Key findings (fakes only)

- ADK's `AnthropicLlm` takes a plain `AsyncAnthropic`; `RetryingClaude` already overrides
  `_anthropic_client`; a full ADK turn reached a fake client with 21 tools.
- Claude turns are broken on base: `BuiltInPlanner` `ThinkingConfig` without a budget makes ADK
  2.10's adapter raise `ValueError` before sending. `thinking_budget=-1` → adaptive, works.
- `AsyncAnthropic()` without a key constructs fine (fails at request time), so the provider must
  check the key itself. SDK errors and client repr don't contain the key.
- WS `agent_error` frames carry `str(exc)` (existing behaviour); keep exception messages key-free.

## Files owned (pending the grant)

See plan.md "Source code". New: `wcl_agent/llm/provider.py`, three backend test files, one frontend
test file. Edits: `vertex.py`, `model_retry.py`, `agent.py`, `config.py`, `greeting.py`,
`main.py` (`_boot` only), `model_state.py`, `api/ws.py` (`chat()` model resolution only),
`test_vertex.py`, `.env.example`, `README.md`. Never: `CLAUDE.md`, `.specify/feature.json`
(restore before each commit), `models.py`, `_load_models`, 035's and 034's files.

## Scrum-master conditions (plan gate)

- Forwarders stay thin (no logic); 033/035 delete them later.
- A pin test for ADK's `_build_anthropic_kwargs` / `_anthropic_client` (T013).
- A "vertex unchanged" regression test: unset and `vertex` give today's literal values for every
  role, model list and discovery mode (T020).
- 035 owns `wcl_agent/llm/generation.py`; don't create it; no dispatch in `provider.py`. The
  contract was snapshotted by the scrum master: report any change to it.

## Open questions

- drop_block behaviour is verified against docs and request shape only; the owner's live check
  confirms it.

## How to resume

1. Read this file, `plan.md`, `tasks.md`, `contracts/provider-layer.md`.
2. Check messages from the scrum master for OWNER GO, the grant and the contract answer.
3. Start `/speckit-implement` at T001; mark tasks `[X]`; full suite after each phase.
