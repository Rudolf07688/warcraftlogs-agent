<!--
SYNC IMPACT REPORT
==================
Version change: TEMPLATE (unversioned placeholders) → 1.0.0
Bump rationale: First concrete ratification. All placeholder tokens replaced with
project-specific principles derived from documentation/ai_guide.md, README.md, and
the wcl_agent/ source. No prior versioned constitution existed, so this is an
initial adoption rather than an amendment.

Modified principles (placeholder → concrete):
  [PRINCIPLE_1_NAME] → I. Answer Anything the Data Supports
  [PRINCIPLE_2_NAME] → II. Grounded Answers Only (NON-NEGOTIABLE)
  [PRINCIPLE_3_NAME] → III. Tools Are Contracts
  [PRINCIPLE_4_NAME] → IV. Thin Core, Interchangeable Surfaces
  [PRINCIPLE_5_NAME] → V. Verify Against the Live API Before Trusting
  (added)            → VI. Respect the Budget, Protect the Secrets

Added sections:
  - Technology & Architecture Constraints (replaces [SECTION_2_NAME])
  - Development Workflow & Quality Gates (replaces [SECTION_3_NAME])

Removed sections: none

Templates requiring updates:
  ✅ .specify/templates/plan-template.md — "Constitution Check" gate is generic
     ("[Gates determined based on constitution file]"); resolves against the
     Constitution Check Gates listed below. No edit required.
  ✅ .specify/templates/spec-template.md — no constitution-coupled sections; the
     spec stays implementation-agnostic per Principle IV. No edit required.
  ✅ .specify/templates/tasks-template.md — phase structure already accommodates
     the principle-driven task types this constitution mandates (tool-contract
     tasks, live smoke-verification tasks, documentation tasks). No edit required.
  ✅ .specify/templates/checklist-template.md — generic; no edit required.
  ⚠ documentation/ai_guide.md — remains the authoritative runtime guidance doc and
     is referenced by Governance. Update its §7 recipe and §10 status whenever a
     principle here changes the tool-authoring contract.

Follow-up TODOs: none. RATIFICATION_DATE set to 2026-09-30, the date of initial
repository history and of this adoption.
-->

# Warcraft Logs Agent Constitution

## Core Principles

### I. Answer Anything the Data Supports

If a question is answerable from Warcraft Logs data, this system MUST be able to
reach an answer. Capability gaps are bugs, not boundaries.

- Every user-facing surface MUST expose a raw-GraphQL escape hatch
  (`run_wcl_graphql`) so the agent can compose a query when no purpose-built tool
  fits.
- The agent instruction MUST direct the model to use the escape hatch rather than
  reply that it cannot answer.
- A repeatedly used escape-hatch query is a signal to promote it to a first-class
  tool; promotion MUST NOT remove the escape hatch.
- "The API does not expose this" is a valid answer. "I don't have a tool for
  that" is not.

**Rationale**: The product's differentiator is coverage — from population-level
spec comparisons down to a single player's per-ability breakdown on one pull. A
fixed tool menu would cap the product at whatever was anticipated on day one.

### II. Grounded Answers Only (NON-NEGOTIABLE)

Every number, name, and ranking presented to a user MUST originate from a tool
result in the current conversation. The model MUST NOT invent, interpolate, or
recall figures from training data.

- Answers MUST state their basis: the encounter, difficulty, partition/season, and
  sample size behind any statistic.
- Derived statistics (percentiles, medians, spec comparisons) MUST be computed from
  returned data in code — not estimated by the model.
- Known data limitations MUST be surfaced, not smoothed over. Leaderboard data is
  the current-season top-of-distribution, not a population sample and not a rolling
  window; answers drawing on it MUST say so.
- When a tool errors or returns nothing, the agent MUST report that and adjust —
  never fill the gap with plausible text.

**Rationale**: A log analyst that confabulates a DPS number is worse than no
analyst — users act on these figures when choosing specs, talents, and rotations,
and a fabricated number is indistinguishable from a real one at a glance.

### III. Tools Are Contracts

A tool is an API consumed by a language model. Its signature and docstring ARE its
schema, and both MUST be treated with the rigor of a public interface.

- Every tool MUST accept primitive arguments (`str`, `int`, `bool`) with sensible
  defaults for optionals. No nested objects, no positional ambiguity.
- Every tool MUST carry a docstring describing its purpose, each argument, and the
  shape of its return value.
- Every tool MUST return a `dict` containing `"status"` (`"success"` or `"error"`),
  with `error_message` populated on failure. Tools MUST NOT raise into the runner.
- Error messages MUST be actionable by the model — they MUST say what to change
  (narrow a filter, fix a class name, correct the GraphQL), not merely what broke.
- Potentially large payloads MUST be size-capped before return, and the cap note
  MUST tell the model how to narrow the request.
- Established argument conventions MUST be preserved across tools: `0` means
  "all/none" for id-shaped arguments; class and spec filters are PascalCase and
  space-free.
- GraphQL enum-valued arguments MUST be whitelist-validated and inlined as enum
  literals; scalar arguments MUST stay typed GraphQL variables.

**Rationale**: The model cannot read the source. Every deviation from these
conventions shows up as a malformed call, a retry loop, and wasted API points.
These are the conventions the current 15 tools already encode; consistency is what
makes the tool surface learnable in one instruction block.

### IV. Thin Core, Interchangeable Surfaces

Domain logic — WCL access, GraphQL composition, statistics, tool definitions —
MUST live in a surface-agnostic core. Every user-facing surface is a thin adapter
over that core.

- The terminal REPL, agent skills, an HTTP/API layer, and a React frontend are all
  peer surfaces. No surface may be the only place a capability exists.
- Core modules MUST NOT import from, or depend on the presence of, any surface. A
  tool MUST NOT print to stdout, prompt for input, or assume a TTY.
- Session context (selected zone, encounter, difficulty, partition) MUST reach
  tools through the session state contract, never through module globals or
  surface-specific storage. Tools read it via their tool context.
- Adding a surface MUST NOT require changing a tool. If it does, the coupling is a
  defect to be fixed before the surface ships.
- Feature specs MUST describe user-visible behavior independent of surface; the
  plan chooses which surfaces deliver it.

**Rationale**: The project is expanding from a single terminal REPL to skills and a
React frontend. Every capability that leaks into `cli.py` or `menu.py` becomes work
to be redone per surface; a clean core makes each new surface additive.

### V. Verify Against the Live API Before Trusting

GraphQL type and shape errors surface only at call time. Code that has never
executed against the real Warcraft Logs API is unverified.

- Any new or modified tool MUST be smoke-tested against a live report, character,
  or encounter before it is considered done, and the verification MUST be reported
  honestly — including what was not exercised.
- Automated tests, where present, MUST run against recorded/mocked GraphQL
  responses so the suite is deterministic and costs zero API points. Mocks MUST be
  captured from real responses, never hand-authored from assumption.
- Every tool MUST have at least a contract-level check that it imports, registers,
  and exposes a well-formed schema.
- Regressions found in production behavior MUST gain a test before the fix merges.
- Discovered API quirks MUST be recorded in `documentation/ai_guide.md` §9 so they
  are learned once, not per contributor.

**Rationale**: The WCL v2 schema is full of traps already paid for in debugging
time — `events` is a paginator not a scalar, rankings carry no `rankPercent`,
`count` is per-page, and the two `metric` enums are different types. Live
verification is how those are caught; the gotcha log is how they stay caught.

### VI. Respect the Budget, Protect the Secrets

API points are a finite shared resource and credentials are never project data.

- Credentials MUST come from the environment. No secret, token, or client ID may be
  committed, logged, echoed in an error message, or embedded in a tool result.
- Expensive operations — deep paging, large `events` pulls — MUST be bounded by an
  explicit cap, and the cap MUST be documented in the tool's docstring.
- The rate-limit budget MUST remain inspectable at runtime via a tool the agent can
  call on its own initiative.
- All WCL access MUST be read-only. No tool may mutate Warcraft Logs state.
- Any surface exposed beyond the local machine (HTTP API, hosted frontend) MUST
  keep WCL and model credentials server-side; they MUST NOT be shipped to a
  browser.

**Rationale**: The client's budget is 720 points/hour — a handful of unbounded
paging calls exhausts it and takes the product down for the hour. And the moment a
web surface exists, a leaked key is a public liability rather than a local one.

## Technology & Architecture Constraints

**Current stack** (changes require an amendment or a documented Complexity Tracking
entry in the feature plan):

- **Language**: Python `>=3.10`, pinned to 3.13 via `.python-version`.
- **Dependencies**: managed exclusively with **uv**. `uv sync` to install,
  `uv run …` to execute. `uv.lock` MUST be committed and MUST stay in sync with
  `pyproject.toml`.
- **Agent framework**: Google ADK. Tools are plain Python functions registered on
  the root agent; ADK derives their schemas from type hints and docstrings.
- **Model**: Gemini via Vertex AI with gcloud ADC. The model identifier MUST remain
  configurable in one place, not scattered across surfaces.
- **Data source**: Warcraft Logs v2 GraphQL API over OAuth2 client credentials, via
  the shared in-process client singleton. New code MUST reuse that client rather
  than opening its own session.
- **Analysis**: pandas for distribution and percentile math.

**Expansion constraints** (skills, frontend, and beyond):

- New surfaces MUST consume the existing core per Principle IV. A React frontend
  talks to a documented server-side API; it MUST NOT reimplement WCL access or
  statistics in TypeScript, and MUST NOT hold WCL or model credentials.
- Agent skills MUST be composed from existing tools where the capability already
  exists; a skill that duplicates tool logic is a defect.
- Every added runtime dependency MUST be justified in the feature plan against the
  simplest alternative. Prefer extending a module over adding a package.
- Runtime values that vary by season or patch — zone ids, encounter ids, difficulty
  ids, partitions — MUST be discovered from the API at runtime. Hardcoding them is
  prohibited outside of test fixtures.
- Persistence, when introduced, MUST arrive behind the existing session-service
  abstraction rather than as direct storage calls from tools or surfaces.

## Development Workflow & Quality Gates

**Constitution Check gates** — a feature plan MUST pass all of these before Phase 0
research, and MUST be re-checked after Phase 1 design:

1. **Coverage**: Does the feature preserve the escape hatch and leave no question
   type newly unanswerable? (Principle I)
2. **Grounding**: Does every user-visible figure trace to a tool result, with its
   basis and limitations stated? (Principle II)
3. **Tool contract**: Do all new or changed tools use primitive args, full
   docstrings, `status` dicts, actionable errors, and size caps? (Principle III)
4. **Surface independence**: Does domain logic land in the core, with surfaces kept
   thin and tools free of surface dependencies? (Principle IV)
5. **Verification**: Is there a live smoke-test plan for new API paths and a
   deterministic mocked test plan for automated coverage? (Principle V)
6. **Budget & secrets**: Are expensive calls bounded, credentials environment-only,
   and all access read-only? (Principle VI)

**Workflow requirements**:

- Work proceeds through the Spec Kit flow: constitution → specify → plan → tasks →
  implement. Specs describe user-visible behavior; plans choose the technology.
- Violations of a gate MUST be recorded in the plan's Complexity Tracking table
  with the rejected simpler alternative. An unrecorded violation blocks the plan.
- Adding a tool MUST follow the recipe in `documentation/ai_guide.md` §7: implement,
  register in `agent.py`, update the agent instruction if it introduces a new
  workflow, then smoke-test live.
- `documentation/ai_guide.md` is the handoff contract for any agent or contributor
  joining with zero context. Any change to the architecture, tool inventory, API
  facts, or discovered gotchas MUST update it in the same change.
- Completion MUST be reported honestly: what was verified, how, and what was left
  untested.

## Governance

This constitution supersedes conflicting practices, conventions, and habits
elsewhere in the project. Where a document and this constitution disagree, this
document wins and the other MUST be corrected.

**Amendment procedure**:

1. Propose the change with its rationale and the principles or sections affected.
2. Assess the impact on `.specify/templates/*` and on
   `documentation/ai_guide.md`, and update them in the same change.
3. Update the version and `Last Amended` date, and prepend a Sync Impact Report to
   this file.
4. Amendments are adopted by the project owner.

**Versioning policy** (semantic versioning):

- **MAJOR**: a principle is removed or redefined in a backward-incompatible way, or
  governance rules change such that prior-compliant work is now non-compliant.
- **MINOR**: a principle or section is added, or existing guidance is materially
  expanded.
- **PATCH**: clarifications, wording, and typo fixes that do not change what is
  required.

**Compliance review**:

- Every feature plan MUST complete the Constitution Check gates above, both before
  research and after design.
- Every code review MUST verify the tool contract (Principle III) and the grounding
  rules (Principle II) for any change touching tools or agent instructions.
- Complexity MUST be justified in writing, not assumed. When a simpler approach was
  rejected, the plan MUST say why.
- `documentation/ai_guide.md` provides runtime development guidance and MUST be
  kept current as part of the change that makes it stale.

**Version**: 1.0.0 | **Ratified**: 2026-09-30 | **Last Amended**: 2026-09-30
