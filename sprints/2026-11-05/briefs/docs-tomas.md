# Docs brief (tier S): architecture docs + spec as-built notes, Tomas

- **Seat:** `dev-2` (Tomas). Alone this round; no other developer runs.
- **Tier:** S. Work **directly on the sprint branch** `sprint-2026-11-05` (tip `70ba94d`) in the sprint worktree `/home/rudolf/dev/wcl-worktrees/sprint` — the docs pass is the last change before the review, and the PO merges nothing meanwhile. Commit there; never push.
- **Security-core:** no. **Migration:** none.

## Do
1. Follow `documentation/architecture/pages/maintaining.html`. `python3 .claude/team/archdocs.py changed` lists the pages whose code moved since their stamp: agent, backend-api, database, deployment, frontend, knowledge-base, observability. Re-verify each listed section **against the code** (not the specs), add what this sprint built (058 data stores: Postgres/Redis exporters, pg_stat_statements + monitor role (0022), sqlcommenter, Postgres file log -> Alloy -> redaction -> Loki, cAdvisor, self-metrics, D9-D11, alerts; 059: Pyroscope opt-in (`WCL_PROFILES`), server-root span profiles, one SQL tracer per engine, finish-reason / conversation-depth / embedding metrics incl. failures, service map, spanmetrics version transform; 060: route errorElement + panel boundaries with reset keys, Faro chat events, D5, D12 + `commits.py`, redaction e2e), remove what is gone (the docker-proxy never shipped; Docker logs are not a Postgres path), and update `index.html` (layer table, system diagram) where a layer changed.
2. Then `archdocs.py stamp` and `archdocs.py check` (must be clean; `changed` must be empty). Screenshot each changed page (headless chrome, window taller than the page) and look at them.
3. `specs/telemetry_spec.md`: add short "As built (2026-11-05, features 058-060; the code wins)" notes where sprint 3 changed the design, in the same style as the existing §8.3 note (QA SPEC-005): §6.7 profiling, §7.1 (D5, boundaries), §7.2 Postgres (file log, monitor role, commenter options), §7.3, §7.4, §8.2 (D5, D9-D12 uids and folders), §8.4 (the two alerts that exist). Short, factual.

## Footprint
`documentation/architecture/**`, `specs/telemetry_spec.md`. Nothing else.

## Hand-off
Board `handoff` + final result: commits, pages changed, `archdocs.py check` output, screenshots looked at. Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
