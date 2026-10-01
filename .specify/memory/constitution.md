<!--
SYNC IMPACT REPORT
Version change: (unratified template) → 1.0.0
Bump rationale: Initial ratification — placeholders replaced with concrete,
  project-specific principles and governance. MAJOR baseline (1.0.0).

Principles defined:
  I.   Strict DRY & Reuse-First
  II.  Methodical, Step-Wise Delivery
  III. Simplicity First (YAGNI) — NON-NEGOTIABLE
  IV.  Typed Data Contracts (Pydantic & Dataclasses)
  V.   Async Python Backend (FastAPI + asyncio)
  VI.  Repo Awareness via GitNexus

Added sections:
  - Technology Stack & Standards
  - Development Workflow & Quality Gates

Removed sections: none (template placeholders replaced in place)

Templates reviewed for consistency:
  ✅ .specify/templates/plan-template.md  — Constitution Check gate is generic; aligns
  ✅ .specify/templates/spec-template.md  — no constitution-mandated sections added; aligns
  ✅ .specify/templates/tasks-template.md — task categories already cover these principles; aligns
  ✅ README.md / documentation/ai_guide.md — runtime guidance consistent with stack

Deferred / follow-up TODOs:
  - Python version: constitution mandates 3.14; repo currently pins 3.13
    (.python-version) due to earlier dependency-wheel caution. Reconcile by
    upgrading the pin to 3.14 (and verifying `uv sync`) or recording an
    explicit, time-boxed exception in Complexity Tracking.
  - FastAPI backend and React frontend are target architecture; the current
    terminal app (`wcl`) is the seed. No exception needed until endpoints/UI exist.
-->

# WCL Agent App Constitution

## Core Principles

### I. Strict DRY & Reuse-First

Every behavior has exactly one authoritative implementation. Before writing new
code, authors MUST search for an existing function, model, query, or utility that
already does the job and reuse or extend it. Duplicated logic, copy-pasted blocks,
and parallel sources of truth are defects, not shortcuts.

- Shared constants, schemas, and GraphQL/query strings live in one module and are
  imported everywhere they are needed (e.g. one WCL client, one class/spec map).
- When the same pattern appears a third time, it MUST be factored into a shared
  helper.

**Rationale**: Single-source-of-truth code is cheaper to change correctly and is
the main defense against drift and subtle inconsistency bugs.

### II. Methodical, Step-Wise Delivery

Work proceeds in small, verifiable steps: understand → plan → implement one slice
→ verify → repeat. Authors MUST NOT make sweeping, multi-concern changes in a
single unreviewed leap.

- Each change is scoped to one concern and left in a working, verifiable state.
- Verification (run it, test it, or demonstrate it) happens before moving on.
- Larger efforts are broken into independently testable increments (MVP first).

**Rationale**: Incremental, verified progress catches mistakes early and keeps the
codebase shippable at every step.

### III. Simplicity First (YAGNI) — NON-NEGOTIABLE

Choose the simplest design that satisfies the current requirement. Do not build
for speculative future needs. Abstractions, layers, and configuration options MUST
earn their place by solving a real, present problem.

- Prefer plain functions and direct calls over frameworks-within-frameworks.
- Any added complexity (extra service, pattern, or dependency) MUST be justified
  in the plan's Complexity Tracking table; unjustified complexity is rejected.

**Rationale**: Overcomplicated systems are slow to build, hard to reason about, and
expensive to maintain; simplicity is a feature.

### IV. Typed Data Contracts (Pydantic & Dataclasses)

Data that crosses a boundary MUST be represented by an explicit typed model, never
an ad-hoc untyped dict passed between layers.

- **Pydantic models** for data entering or leaving the system: API request/response
  bodies, messages, and externally sourced payloads that require validation.
- **Dataclasses** for internal value objects and configuration passed around in
  process.
- Public function signatures use type hints; boundary inputs are validated at the
  edge, so internal code can trust its data.

**Rationale**: Explicit, validated contracts make interfaces self-documenting,
catch malformed data at the boundary, and make refactoring safe.

### V. Async Python Backend (FastAPI + asyncio)

The backend is Python. All HTTP endpoints MUST be served with **FastAPI** using
**asyncio** (`async def` handlers and non-blocking I/O).

- Network/API/database calls on the request path MUST be async; blocking work is
  offloaded (e.g. thread/executor) rather than stalling the event loop.
- Endpoints accept and return Pydantic models (Principle IV).

**Rationale**: A single async framework keeps I/O-bound work (the dominant cost in
this app — external API calls) efficient and the backend consistent.

### VI. Repo Awareness via GitNexus

Before changing unfamiliar code, authors MUST use **GitNexus** to explore the
repository and confirm they understand the affected code paths, callers, and
dependencies. Changes based on assumption rather than verified understanding are
not permitted.

- Use GitNexus to trace execution, find callers/impact, and understand structure
  before editing; use it again to assess blast radius before risky changes.

**Rationale**: Understanding the real call graph before editing prevents breakage
and is the prerequisite for safe DRY reuse (Principle I).

## Technology Stack & Standards

The project standardizes on the following stack; deviations require a recorded
exception (see Governance).

- **Language/Runtime**: Python **3.14**.
- **Package & environment management**: **uv** (`uv sync`, `uv add`, `uv run`);
  dependencies declared in `pyproject.toml` with a committed `uv.lock`.
- **Backend**: **FastAPI** + **asyncio** for all endpoints.
- **Data modeling**: **Pydantic** (boundary/validated data) and **dataclasses**
  (internal config/value objects).
- **Frontend**: **React**.
- **Secrets**: never committed; provided via environment / `.env` (gitignored),
  with a tracked `.env.example` template.
- **Best practices**: code is formatted, linted, and type-checked; follows
  idiomatic conventions of each tool/framework; no dead code or committed secrets.

## Development Workflow & Quality Gates

- **Understand before you change**: explore with GitNexus (Principle VI) first.
- **Plan then build**: non-trivial work follows the Spec Kit flow
  (specify → plan → tasks → implement) in methodical, step-wise increments
  (Principle II).
- **Constitution Check gate**: every plan MUST pass a Constitution Check before
  implementation; violations are either removed or justified in the plan's
  Complexity Tracking table.
- **Reuse check**: before adding code, confirm no existing implementation covers
  the need (Principle I).
- **Verification**: each increment is run/tested/demonstrated before it is
  considered done.
- **Commit discipline**: commits are scoped and descriptive; secrets are never
  committed; `.gitignore` is kept current.

## Governance

This constitution supersedes other practices when they conflict. All plans,
reviews, and implementations MUST verify compliance with these principles.

- **Amendments**: proposed as a change to this file with a clear rationale, and
  take effect once committed. Dependent templates and guidance docs MUST be updated
  in the same change when an amendment affects them.
- **Versioning (semantic)**: MAJOR for backward-incompatible principle removals or
  redefinitions; MINOR for a new principle/section or materially expanded guidance;
  PATCH for clarifications and non-semantic refinements.
- **Compliance & exceptions**: complexity or stack deviations MUST be justified in
  the plan's Complexity Tracking table; unjustified violations block the work.
- **Runtime guidance**: `documentation/ai_guide.md` and `README.md` provide
  operational guidance and MUST stay consistent with this constitution.

**Version**: 1.0.0 | **Ratified**: 2026-10-01 | **Last Amended**: 2026-10-01
