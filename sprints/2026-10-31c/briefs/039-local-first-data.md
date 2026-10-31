# Brief 039: local-first data (epic 103, first slice)

- **Feature / branch:** 039, `039-local-first-data`
- **Tier:** M (one Spec Kit pass: specify, clarify (self-answered), plan, tasks, implement; no
  gates in between). Record each clarify answer on the board (`--key clarify:039-<topic>`).
- **Seat:** `dev-1` (Ansel). Model opus, effort high.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (detached at `a5b84de`). Create your
  branch from the sprint tip:
  `git -C /home/rudolf/dev/wcl-worktrees/dev-a switch -c 039-local-first-data sprint-2026-10-31c`.
- **Base ref:** `sprint-2026-10-31c` (tip `a5b84de` at launch).
- **Parallel developer:** Tomas (`dev-2`) on feature 040 in `/home/rudolf/dev/wcl-worktrees/dev-b`.
  His footprint is listed below; don't touch it.
- **Product owner:** Maren (`maren` on the board).
- **Migration assigned:** `0018_<short_name>`, `down_revision = "0017_proposal_user_rls"`. You
  are the only developer adding a migration this sprint.
- **Throwaway Postgres:** your own container, e.g. `wcl-039-pg` on port **15439** (`postgres:17`;
  recipe in `specs/036-profile-write-hardening/quickstart.md` §2, alembic needs
  `-c backend/alembic.ini`). Never the compose `db`. Stop it when done.
- **Tests:** run in a clean env: `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`
  (shells may carry live app env vars). No live WCL or LLM calls: fakes and fixtures only.

## Autonomy (owner preference 16)

The owner has given the whole team autonomy: "I value your initiative, your recommendations
and your learnings as an individual. I want to give you autonomy as much as possible." Within
this brief, decide, act and explain afterwards: post each real decision on the board as
`decision` (`--key scope:039:<topic>`) with its reason. Don't ask what the steer, code, specs
or a sensible default answer. Return "blocked: ..." only for what is genuinely not yours: a
file outside your footprint you can't avoid, an irreversible action, scope beyond these
stories. In your hand-off include a short "Autonomy" section: the decisions you made without
asking, and which you'd make differently.

## The owner's steer for this feature (board #1)

- **Design note on the board before code.** After `/speckit-plan`, post a `decision` with key
  `design:039` (a short summary plus the path to your plan/research) covering: the visibility
  rule's data model, how "a code the user already references" is computed, the read path order
  (Redis → raw_fetches → WCL), the freshness rule per data family, and what happens on a
  private/deleted report. Then carry straight on; it is not a gate, but I read it and may
  override by a later entry on the same key.
- **Visibility rule (owner-approved, sc-178):** share stored data with a user only for **public
  reports**, or **report codes that user (their tenant) already references**. When a refresh
  finds a report **private or deleted**, **delete the stored copy**. Otherwise keep finished
  reports **indefinitely** (no age-based retention).
- **Order:** sc-178 → sc-177 → sc-129. **If sc-178 runs long, drop sc-129 rather than rush
  it.** Tell me on the board (`--key status:039`) if you drop it; that's a legitimate outcome.
- **Security checks:** one bypass attempt on the visibility rule before hand-off (describe it
  in the hand-off: what you tried and what stopped it). I make a second one at merge.

## Context you'll want

- `raw_fetches` (feature 020, migration `0013_raw_fetches.py`) is global, not tenant-scoped, and
  nothing reads it yet. Writer: `backend/app/services/fetch_persistence.py` (sink set via
  `wcl_agent.client.wcl_client.set_fetch_sink`); upsert: `backend/app/repositories/raw_fetches.py`.
- The shared Redis WCL cache (feature 014, `wcl_agent/cache/cache.py`) already serves cached
  results across tenants per key. Your design note must say how the visibility rule relates to
  it. At minimum: DB-first reads must not widen exposure beyond what exists today, and deleting
  a private/deleted report's stored copy should also evict its Redis keys. Don't redesign the
  Redis layer beyond that; anything bigger becomes a Backlog ticket.
- The request identity is `backend/app/tenancy/context.py::current_identity` (set per turn in
  `backend/app/api/ws.py`, which is Tomas's file this sprint: read the contextvar, don't edit ws.py).
- The tenant's references to report codes probably live in tracked raids, recent raids / M+
  runs, conversation artifacts or profile data; find the right set and justify it.

## Stories

Read each in full (`mcp__shortcut__stories-get-by-id`). Move each to In Progress (`500000008`)
when you start it and to Under Review (`500000023`) in your hand-off. Never Done.

### sc-178 (2 pts, High): QA SEC-001: guard raw_fetches against cross-tenant exposure before anything reads it

Story text (verbatim):
> As a user, I want the lookups I trigger (character names, unlisted report codes) to stay
> private to my workspace, even though the raw WCL store is global.
>
> QA ID: SEC-001 (Low today; Medium once something reads the table)
> Location: migration `0013_raw_fetches.py`, `backend/app/repositories/raw_fetches.py`
> Problem: `raw_fetches` is global (decision 6) and stores the full query params, so it records
> what each tenant looked up, including unlisted report codes. Rows are never deleted, so a
> report its owner later deletes or makes private stays stored. Nothing reads the table yet, so
> there's no leak today. DB-first reads (sc-129) or semantic search (epic 100) would expose it
> across tenants unless they are designed for it.
> Suggested fix, a design gate for sc-129 and sc-111..115: serve a raw row to a tenant only when
> that tenant could fetch it itself (public data, or a code the tenant already references), or
> record which tenant first fetched each row; decide on a revocation and retention rule for
> deleted or private reports.

Acceptance criteria (PO):
1. A stored raw row is served to a tenant only if its report is public, or its report code is
   one that tenant already references (the owner's rule above). Non-report data (e.g. character
   rankings, which WCL serves publicly) follows a rule you state in the design note.
2. The rule is enforced in one place (a single read function/repository), so sc-129 and later
   epic-100 work can't bypass it by querying the table directly.
3. When a WCL refresh finds a report private or deleted, every stored row for that code is
   deleted (and its Redis keys evicted).
4. Finished reports are kept indefinitely otherwise; no age-based purge.
5. Tests: tenant A can't get a row only tenant B references (unlisted/private code); a public
   report row is shared; a private/deleted refresh deletes the rows. Postgres-backed where the
   behaviour depends on Postgres (run them on your throwaway container and say so).

### sc-177 (3 pts): QA PERF-002/PERF-003/SEC-003: raw_fetches write amplification, unbounded growth and writer edge cases

Story text (verbatim):
> As the app owner, I want the raw WCL fetch store (feature 020) to stay cheap as it grows, so
> Postgres doesn't bloat before anything reads it.
>
> Locations: `backend/app/repositories/raw_fetches.py` (upsert),
> `backend/app/services/fetch_persistence.py` (one commit per row, `_Throttle`), migration
> `0013_raw_fetches.py`
> Problems:
> - Every refetch of an uncached heavy call rewrites an identical multi-hundred-KB JSONB payload
>   (WAL, dead rows), committing once per row.
> - No retention or size limit (accepted in the spec, but storage cost is unknown, estimated at
>   several GB a month), and any signed-in user can drive growth through agent fetches.
> - Edge cases: `report_code` String(32) and `operation_name` String(120) overflow, a `\u0000` in
>   a body (JSONB rejects it), the throttled warning's final count never logged, and DB errors
>   may log query params.
> Suggested fix: skip the update when the payload is unchanged (hash compare); batch commits;
> add a monitoring query plus a retention policy for the owner to decide on; widen or truncate
> the columns, strip NUL, flush the throttle count on stop.

Acceptance criteria (PO):
1. An unchanged payload doesn't rewrite the row (hash compare or equivalent); a changed one does.
2. The writer commits in batches, not once per row, without losing the "a failure never reaches
   the caller" property.
3. Overlong `report_code` / `operation_name` values and a `\u0000` in a body are handled (no
   failed insert); the throttled warning's pending count is flushed on stop; DB error logs don't
   include query params.
4. Retention follows the owner's rule (keep finished reports; delete on private/deleted, from
   sc-178). Add a documented monitoring query for table size and row count (in the quickstart
   or the architecture doc); no age-based purge.
5. Tests for each point.

### sc-129 (5 pts, High): DB-first reads with freshness rules

Story text (verbatim):
> As a user, I want fetches served from the DB when fresh enough (finished reports never change;
> live data expires), layered with Redis, so repeat questions are fast.

The story has no ACs; the owner asked that they be written in your design. My draft below;
refine it in the spec, and post any change on `design:039`.

Acceptance criteria (PO draft):
1. A WCL read checks Redis, then the store, then WCL. A finished report's data is served from
   the store with no WCL call; live/unfinished data and other families follow a freshness rule
   per family (state it in the design; reuse the existing cache families where they fit).
2. Every store read goes through the sc-178 visibility function; a row the tenant may not see
   is treated as a miss (fetch from WCL, which enforces WCL's own permissions).
3. A store hit back-fills Redis, so the next read is a Redis hit.
4. Any store failure falls back to WCL; a turn never fails because of the store.
5. Tests: finished-report hit with no WCL call; stale live data refetched; a hidden row is a miss;
   store error falls back. One test proves the CLI/eval path (no sink, no DB) is unchanged.

## File footprint (stay inside it)

`backend/app/repositories/raw_fetches.py`, `backend/app/services/fetch_persistence.py`, new
`backend/app/services/raw_fetch_*.py` (or a new repository module next to raw_fetches),
`backend/app/db/models.py`, `backend/migrations/versions/0018_*`, `backend/app/main.py`
(lifespan wiring only), `backend/app/config.py`, `wcl_agent/client/*`, `wcl_agent/cache/*`,
`documentation/architecture/backend-data-infra.html`, `specs/039-*`, and tests under
`backend/tests/` for these.

**Not yours (Tomas, feature 040):** `backend/app/agent_runner.py`, `backend/app/api/ws.py`,
`wcl_agent/llm/model_retry.py`, everything under `frontend/`. Tomas won't edit
`wcl_agent/cache/cache.py` (he resets the refresh-actor via its existing setter in ws.py). If you
truly need one of his files, post a `question` with `--key owner:<path>` and carry on with the
rest; I arbitrate. Never commit `CLAUDE.md`, `AGENTS.md`, `todo.md`,
`.specify/memory/constitution.md` or `.specify/feature.json` (restore them before each commit).

## Done means

- All ACs met (or sc-129 dropped by the rule above, with the reason on the board).
- `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q` green; the Postgres tests run and
  green on your container (give the command in the hand-off). Migration upgrade and downgrade
  both work.
- GitNexus impact before each symbol edit (HIGH/CRITICAL risks as a board `notice`);
  `detect-changes --scope all --repo .` before each commit. Commits end with
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Live checks for the owner: post one board `question` with key `live-check:039` listing what
  team-lead should try on the merged branch (e.g. ask the same report question twice and see no
  second WCL call). Team-lead batches them.
- Never push, never merge. Hand-off as your final result: branch, commits, files, test counts
  (SQLite and Postgres), risks, AC mapping per story, the bypass attempt, the live-check list,
  and the Autonomy section. Update your memory at the end (light).
