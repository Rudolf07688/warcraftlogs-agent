# Checkpoint (039): before implementation

- **Decisions**: board `clarify:039-*` (#17-#21) and `design:039` (#24). Read research.md R1-R9.
- **Files**: see plan.md Source Code. Footprint only (brief); ws.py / agent_runner.py are Tomas's.
- **Start at**: T001 (PG container 15439), then T002 migration 0018 and the models, then US1.
- **Commit per story** (crash safety). Restore `CLAUDE.md` and `.specify/feature.json` before
  each commit.
- **Key invariants**: store read happens in the caller's context, before single-flight; a store
  hit is never offered and never grants; non-report rows are never served; gone = single-code
  query with `reportData.report: null`.
