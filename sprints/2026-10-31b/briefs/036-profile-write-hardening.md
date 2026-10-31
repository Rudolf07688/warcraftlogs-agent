# Brief 036: profile write-path hardening (epic-203 QA debt)

- **Feature / branch:** 036, `036-profile-write-hardening`
- **Tier:** M (one Spec Kit pass: specify, plan, tasks, implement; no gates in between). Answer
  your own clarify questions and record each answer on the board (`--key clarify:036-<topic>`).
- **Seat:** `dev-1`. Worktree: `/home/rudolf/dev/wcl-worktrees/dev-a` (detached at `7989d61`).
  Create your branch there from the sprint tip: `git -C /home/rudolf/dev/wcl-worktrees/dev-a
  switch -c 036-profile-write-hardening sprint-2026-10-31b`.
- **Base ref:** `sprint-2026-10-31b` (tip `7989d61` at launch).
- **Parallel developer:** seat `dev-2` on feature 037 in `/home/rudolf/dev/wcl-worktrees/dev-b`
  (see `member.py roster` for their name). Their footprint is listed below; don't touch it.
- **Product owner:** Maren (`maren` on the board). Model opus, effort high.
- **Migration assigned:** `0017_<short_name>` (e.g. `0017_proposal_user_rls`),
  `down_revision = "0016_profile_proposals"`. You are the only developer adding a migration
  this sprint.

## Autonomy (owner preference 16, passed on to every brief)

The owner has given the whole team autonomy: "I value your initiative, your recommendations
and your learnings as an individual. I want to give you autonomy as much as possible." Within
this brief, decide, act and explain afterwards: post each real decision (design choice, an AC
interpretation, a trade-off, something you chose not to do) on the board as `decision` with
its reason. Don't ask what the steer, code, specs or a sensible default answer. Return
"blocked: ..." only for what is genuinely not yours to decide: a file outside your footprint
you can't avoid, an irreversible action, scope beyond these stories. In your hand-off,
include a short "Autonomy" section: the decisions you made without asking and which you'd make
differently. Write your lesson on autonomy into your memory at the end.

## Stories (do them in this order; sc-221 first)

Read each story in full first (`mcp__shortcut__stories-get-by-id`); its description is the
source. Move each to In Progress (`500000008`) when you start it and to Under Review
(`500000023`) in your hand-off. Never Done.

### sc-221 (3 pts, High): QA SEC-001/002/003: harden the agent profile write path against injected log text

Story text (verbatim):
> As a user, I want Barnaby to propose profile changes only when I ask for them, and the card
> to show only clean, bounded text, so that a crafted Warcraft Logs report can't talk me into
> changing my profile.
>
> Locations: `backend/app/services/profile_context.py:142` (RECENT RUNS uses `raid.title`),
> `backend/app/agent_tools/profile_tools.py:27`, `wcl_agent/capabilities.py:33`,
> `backend/app/services/profile_proposals.py:53, 168-172`,
> `frontend/src/components/ProposalCard.tsx:119-129`
> Problems:
> - Uploader-controlled report titles now go into every turn's preamble without being marked
>   as untrusted. Together with tool results, they could push the model to propose unrequested
>   changes, removals included. The approval card is the only stop.
> - `class_name` and `spec` aren't length-limited and are stored and shown on the card.
>   Invalid hostile names (up to 100 chars) are also shown next to Approve.
> - The realm rule allows 40 characters of short prose, which would persist into every later
>   preamble after approval.
> Suggested fix: use only `zone_name` (or mark the block as untrusted data); add an instruction
> rule that proposals need a request in the user's own message; clip or roster-map
> class/spec; on the card, show invalid items by reason only; check realms against a
> known-realm list, or render them as slugs.

Acceptance criteria (PO):
1. No uploader-controlled report title reaches the turn preamble unmarked: either the
   RECENT RUNS block uses `zone_name` only, or it is fenced and labelled as untrusted data.
2. The agent instruction (put it in `wcl_agent/capabilities.py`, the profile text near
   line 32-35, not `agent.py`) states that profile proposals need a request in the user's own
   message, never one from tool results, logs or report text.
3. `class_name` and `spec` are bounded (clipped or mapped to the known class/spec roster)
   before storage and display.
4. The card shows invalid items by reason only, never the raw hostile name.
5. A realm that is not a plausible realm (known-realm list or slug form, your call, post it)
   can't persist prose into later preambles.
6. Regression tests for each point (backend unit tests; a frontend test for the card).

### sc-222 (2 pts): QA SEC-004/005: reset the agent identity context and add user-level RLS on profile_proposals

Summary (read the story for the full text): `current_identity.set` at
`backend/app/api/ws.py:289` is never reset, and tasks spawned via
`backend/app/services/background.py:34` inherit it; the RLS policy in
`backend/migrations/versions/0016_profile_proposals.py:33` checks the tenant only.
Suggested fix: reset in `finally`, run `spawn` in a fresh context, add a user-scoped policy.

Acceptance criteria (PO):
1. The identity contextvar is reset when the turn ends (token reset in `finally`), and
   background tasks start without the caller's identity.
2. Migration 0017 adds a user-level RLS predicate on `profile_proposals` (upgrade and
   downgrade both work).
3. Tests: a unit test for the context reset and spawn isolation; a Postgres RLS test (skipped
   without `TEST_DATABASE_URL`, like `backend/tests/test_rls.py`) proving user A can't read
   user B's proposal in the same tenant. **Run it** against a throwaway Postgres container
   (recipe: `specs/034-epic203-qa-fixes/quickstart.md`, use your own name and port, e.g.
   `wcl-036-pg` on 15436; images `postgres:17` is available). Never use the compose `db`
   container or the owner's database. Stop the container when done.

### sc-223 (2 pts): QA SEC-007/BUG-008: profile cap race and legacy realm-spelling duplicates

Summary: the profile cap is check-then-insert with no lock
(`backend/app/db/repository.py:1120-1128`), and `_profile` in
`backend/app/services/profile_proposals.py:107-120` is keyed by identity only, so legacy
duplicate spellings collapse. Suggested fix: serialise adds per tenant, key by
(identity, target).

Acceptance criteria (PO):
1. Concurrent adds can't exceed the cap (a lock, an advisory lock, or a constraint; your call).
2. Legacy realm-spelling duplicates don't collapse into one entry when applying a proposal.
3. Tests for both (the race test may be Postgres-only, like `test_proposal_race_pg.py`).

### sc-225 (2 pts): QA PERF-003/005/006: proposal approve and read DB round trips, guide job fan-out

Summary: a 30-item approve costs about 160 DB round trips (`profile_proposals._apply`,
`backend/app/api/proposals.py::_decide`); reads (`backend/app/api/conversations.py::list_proposals`,
the ws proposal frame read) open extra transactions; approval starts all guide jobs at once
(`spawn` in `backend/app/services/guide.py:373`).

Acceptance criteria (PO):
1. Approve does a bounded number of round trips, not one-per-item multiples (state the
   before/after count in the hand-off).
2. Proposal reads reuse one transaction where the story says they open extra ones.
3. Guide jobs started by an approval are bounded (a semaphore or a queue), not all at once.
4. Existing proposal tests stay green; add a test for the bound.

### sc-244 (1 pt, Low, last): QA SPEC-006/007/009/010: architecture docs and contracts are stale for the self-aware agent

Locations: `documentation/architecture/agent-frontend.html:158, 401, 413, 447, 455, 471-482`,
`documentation/architecture/backend-data-infra.html:280-282, 313, 339, 346, 361`,
`specs/029-agent-profile-proposals/contracts/capability-summary.md:57-58`,
`documentation/designs/self-aware-agent/capabilities-and-tools.html:363`.

Acceptance criteria (PO):
1. The docs describe the proposal frame, the profile tools (`propose_profile_changes`,
   `get_report_participants`), the `profile_proposals` table (including the new user-level
   RLS from sc-222), the proposal routes, and the updated counts.
2. Docs only; no code change.

## File footprint (stay inside it)

`backend/app/services/{profile_context,profile_proposals,background,guide}.py`,
`backend/app/agent_tools/profile_tools.py`, `backend/app/api/{ws,proposals,conversations}.py`,
`backend/app/db/repository.py`, `backend/app/repositories/profile_proposals.py`,
`backend/app/schemas.py`, `wcl_agent/capabilities.py`,
`frontend/src/components/ProposalCard.tsx` (and its test), `backend/migrations/versions/0017_*`,
`documentation/architecture/*`, `documentation/designs/self-aware-agent/*`,
`specs/029-agent-profile-proposals/contracts/*`, `specs/036-*`, and tests under
`backend/tests/` and `frontend/src/**/*.test.tsx` for these.

**Not yours (dev-2, feature 037):** `wcl_agent/agent.py`, `wcl_agent/llm/*`,
`wcl_agent/tools/participants.py`, `wcl_agent/cache/*`, `backend/app/auth/*`,
`backend/app/api/auth.py`, `backend/app/services/{auth_service,conversation_titles}.py`,
`backend/app/config.py`, `frontend/src/components/StreamMarkdown.tsx`. If you truly need one,
post a `question` on the board (`--key owner:<path>`) and continue with the rest; I arbitrate.
Never commit `CLAUDE.md`, `AGENTS.md`, `todo.md`, `.specify/memory/constitution.md` or
`.specify/feature.json`.

## Done means

- All ACs met, `uv run --extra test pytest -q` green, `cd frontend && npm run build && npm test`
  green, the Postgres tests run and green (say so in the hand-off, with the command).
- GitNexus impact before each symbol edit; `detect-changes --scope all --repo .` before each
  commit. Commits end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Never push, never merge. Hand-off as your final result: branch, commits, files, test counts,
  risks, AC mapping per story, owner live checks, and the Autonomy section.
