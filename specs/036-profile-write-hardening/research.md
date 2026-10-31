# Research: Profile write-path hardening

## R1 Realm guard (sc-221 AC5)
- **Decision**: realm-form rule, ≤ 24 characters: words of letters or digits joined by single
  spaces, hyphens or apostrophes, optional `(Suffix)`.
- **Rationale**: the app has no realm list; the longest real realm names are about 22
  characters ("Culte de la Rive noire"). Sentence punctuation and long prose are refused.
- **Alternatives**: a static realm list (≈ 1000 names to maintain); a WCL character lookup per
  item (design 029 open question, answer A; adds a network call per item). Kept as backlog.

## R2 Class/spec bounding (AC3)
- **Decision**: map through `roster.resolve_spec`; class alone if only the class resolves.
- **Alternatives**: clip to N characters (still shows hostile text, just shorter).

## R3 Context isolation (sc-222)
- **Decision**: fresh `contextvars.Context()` per spawned task.
- **Rationale**: all four ContextVars in the code default to a value that is right for a job
  (identity None, refresh actor None, lane set by the job, turn stats None).
- **Alternatives**: copy the context and reset only the identity (keeps leaking the others).

## R4 Cap serialisation (sc-223)
- **Decision**: `pg_advisory_xact_lock` keyed by `hashtextextended('profile:' || tenant, 0)`.
- **Alternatives**: `SELECT … FOR UPDATE` on `tenants` (conflicts with FK `KEY SHARE` locks);
  a DB constraint (a count cap isn't expressible as a constraint).

## R5 Bounded approve (sc-225)
- **Decision**: re-validate under the lock, then bulk insert / update / delete with RETURNING.
- **Rationale**: the per-item savepoint + duplicate check + count existed to catch races; the
  lock removes them. Postgres and SQLite (≥ 3.35) both support RETURNING.
- **Alternatives**: keep savepoints, drop only the re-checks (still one-per-item).
