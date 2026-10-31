# Brief 040: small fixes (live-pass bug, charts on reopen, fail-fast 429s, images, contextvar, scroll)

- **Feature / branch:** 040, `040-small-fixes`
- **Tier:** S (a short plan, then implement; no Spec Kit). Post your plan as a board `notice`
  (`--key plan:040`) and put it in the hand-off.
- **Seat:** `dev-2` (Tomas). Model sonnet, effort high.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b` (detached at `a5b84de`). Create your
  branch from the sprint tip:
  `git -C /home/rudolf/dev/wcl-worktrees/dev-b switch -c 040-small-fixes sprint-2026-10-31c`.
- **Base ref:** `sprint-2026-10-31c` (tip `a5b84de` at launch).
- **Parallel developer:** Ansel (`dev-1`) on feature 039 (raw_fetches / DB-first reads) in
  `/home/rudolf/dev/wcl-worktrees/dev-a`. His footprint is below; don't touch it.
- **Product owner:** Maren (`maren` on the board).
- **No migration, no lockfile or manifest change** this sprint for you.
- **Tests:** run in a clean env: `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`,
  and `cd frontend && npm run build && npm test`. The build dirties
  `frontend/tsconfig.tsbuildinfo`: check it out before committing. No live LLM or WCL calls.

## Autonomy (owner preference 16)

The owner has given the whole team autonomy: "I value your initiative, your recommendations
and your learnings as an individual. I want to give you autonomy as much as possible." Within
this brief, decide, act and explain afterwards: post each real decision on the board as
`decision` (`--key scope:040:<topic>`) with its reason. Don't ask what the code or a sensible
default answers. Return "blocked: ..." only for what is genuinely not yours (a file outside your
footprint you can't avoid, scope beyond these stories). In your hand-off include a short
"Autonomy" section: the decisions you made without asking, and which you'd make differently.

Lesson from last sprint (from your own memory and the team report): your misses were edge cases
you didn't think to try. For each story, write down the two or three edge cases you'll test
before you code. **sc-272 is a security fix: make one bypass attempt before hand-off** and
describe it; I make another at merge.

## Stories (suggested order; one commit per story is fine)

Read each in full (`mcp__shortcut__stories-get-by-id`). Move each to In Progress (`500000008`)
when you start it and to Under Review (`500000023`) in your hand-off. Never Done.

### sc-289 (2 pts, bug): one tool call sends dozens of tool_start frames on the Anthropic provider

Story text (verbatim):
> As a user, I want each tool call to start one spell card, so that the chat doesn't flood the
> socket (or the UI) with repeated tool-start events.
>
> Found in team-lead's live pass of sprint 2026-10-31b (2026-10-31, provider `anthropic`, model
> claude-haiku-5-5): one `propose_profile_changes` call produced 23 `tool_start` frames and 1
> `tool_end`; a two-tool turn (`get_report_participants` + `propose_profile_changes`) produced 79
> `tool_start` frames and 2 `tool_end`.
>
> Likely cause: `backend/app/agent_runner.py:313-325` yields a `tool_start` for every event part
> carrying a `function_call`, and the Anthropic streaming path emits partial events that repeat
> the call while its arguments stream. Not a regression of sprint 2026-10-31b (that code is
> unchanged since 029); probably since 032 (provider switch).
>
> Suggested fix: yield `tool_start` once per call id (skip partial events, or dedupe on
> `call.id`), with a test using a fake stream that repeats a function_call part.
>
> Check: whether the frontend already dedupes (no visible symptom confirmed); verify on Vertex too.

Acceptance criteria (PO):
1. Each tool call produces exactly one `tool_start` per turn, however many partial events repeat
   its `function_call` part. Two distinct calls (even of the same tool) still produce two.
2. The `tool_start` args are the call's final (complete) args, or the frame is sent once the args
   are complete; state which and why.
3. `tool_end`'s `ms` is measured from the call's first start, not reset by repeated partials (the
   current code overwrites `pending_started[call_id]` on every partial).
4. Calls without an id still work (no crash, no flood); say how you dedupe them.
5. Tests with a fake event stream: repeated partials of one call, two calls, a call without an
   id, and the non-partial (Vertex-style) stream unchanged. Note in the hand-off whether the
   frontend dedupes `tool_start` today.

### sc-213 (2 pts): charts and graphs don't come back when a chat is reopened

Story text (verbatim):
> As a user, I want the charts Barnaby made in a chat to show again when I reopen that chat, so
> that old analyses aren't missing their graphs.
>
> Found while designing sc-212 (sprint 2026-10-26, feature 028): `GET /api/conversations/{id}`
> returns `artifacts` with their `message_seq`, but the frontend ignores them on reload.
> `selectConversation` in `frontend/src/App.tsx` (around line 319) maps only `detail.messages`.
> Charts appear live but vanish after a reload or reopening the chat.
>
> Suggested fix: attach `detail.artifacts` to messages by `message_seq` on reload, the same way
> 031 attaches proposals (sc-207).

Comment on the story (2026-10-26): restClient already attaches artifacts to messages by
message_seq on reload, so the symptom is more likely in the figure rebuild or in
`PlotlyArtifact` than in the reload mapping. **Reproduce before fixing** (a test with a stored
artifact payload shaped like the backend's).

Acceptance criteria (PO):
1. The root cause is identified and named in the hand-off (with the evidence).
2. A chart made in a chat renders again after reopening that chat and after a full reload.
3. A frontend test covers the reopen path with a stored artifact. If the bug is in the backend
   payload (e.g. what is stored per artifact), fix it there only if it's in your footprint;
   otherwise post a `question --key owner:<path>`.

### sc-268 (2 pts): QA PERF-002: one wait budget per turn when both models are rate-limited

Story text (verbatim):
> As a user, I want a turn to fail fast when both my model and its sibling are rate-limited, so
> that I don't wait 40–100 s for an error.
>
> Location: `wcl_agent/llm/model_retry.py:350-380` (`generate_with_fallback`)
> Problem: when both models are remembered as limited, every turn still runs the short primary
> probe and then the sibling's full schedule (about 40 s, up to 100 s) before failing.
> Suggested fix: one shared wait budget per turn across primary and sibling (Tomas's backlog
> note, board #28), or a short budget for the sibling when it is remembered too.

Acceptance criteria (PO):
1. When both models are remembered as rate-limited, a turn gives up within one shared wait
   budget (state the number and where it's set) instead of probe + the sibling's full schedule.
2. When only one model is remembered as limited, or none is, behaviour is unchanged.
3. The user still gets the existing clean "both models are busy, try again shortly" outcome.
4. Tests with a fake clock/sleep for: both limited, one limited, none limited.
   Keep new settings as module constants or env reads inside `model_retry.py`
   (`backend/app/config.py` is Ansel's this sprint).

### sc-272 (1 pt, security): same-origin image allowance lets model markdown fire authenticated GETs

Story text (verbatim):
> As a user, I want images in model output not to trigger app actions, so that a crafted log
> can't make my browser call costly endpoints.
>
> Location: `frontend/src/components/StreamMarkdown.tsx:32` (`allowedImagePrefixes: [origin]`)
> Problem: same-origin images still render, so model markdown like `![](/api/...pdf)` fires an
> authenticated GET (for example PDF generation) as soon as it renders.
> Suggested fix: allow no images at all (the app emits none in markdown), or only a static-asset
> path prefix.

Acceptance criteria (PO):
1. No image in model markdown can make the browser request an `/api/...` URL (or any app route
   other than static assets, if you keep a static prefix; your call, post it).
2. Tests: relative `/api/...`, absolute same-origin, protocol-relative, encoded paths, and the
   `<picture>`/`srcset` route that sc-157 closed stay blocked.
3. One bypass attempt before hand-off, described in the hand-off.

### sc-276 (1 pt, security): reset the WCL refresh-actor contextvar after each turn

Story text (verbatim):
> As the operator, I want per-turn context variables reset when the turn ends, so that later
> tasks on the same socket don't act as the previous turn's actor.
>
> Location: `backend/app/api/ws.py` `_handle_turn` (`set_refresh_actor`)
> Problem: `set_refresh_actor` is a ContextVar set per turn and never reset, like
> `current_identity` was before sc-222. That's harmless for spawned jobs now (fresh context), but
> the socket's later in-context tasks (suggestions) still inherit it.
> Suggested fix: reset it with its token in the turn's `finally`, as sc-222 does for the identity.

Acceptance criteria (PO):
1. The refresh actor is cleared when the turn ends (in the turn's `finally`), so later in-context
   tasks on the socket don't inherit it.
2. A unit test proves it.
3. Don't edit `wcl_agent/cache/cache.py` (Ansel's this sprint): clear it through the existing
   `set_refresh_actor(None)` in ws.py. If a token-based reset is really needed, post a
   `question --key owner:wcl_agent/cache/cache.py` and carry on.

### sc-140 (1 pt, ux): scroll to the question when the answer completes

Story text (verbatim):
> As a user, I want the view to scroll to the top of my question when the answer finishes, so I
> read from the start.

Acceptance criteria (PO):
1. When an answer finishes streaming, the chat scrolls so the top of the user's question that
   produced it is at (or near) the top of the view.
2. If the user scrolled away during streaming, don't yank them back (only scroll if they were
   following the stream). Post your exact rule.
3. No scroll jump on reopening an old chat or on follow-up/suggestion frames.
4. A frontend test for the trigger (scroll call made on completion, not otherwise).

## File footprint (stay inside it)

`backend/app/agent_runner.py`, `backend/app/api/ws.py`, `wcl_agent/llm/model_retry.py`,
`frontend/src/**` (components, `App.tsx`, `api/*`, `types.ts`, styles), and tests under
`backend/tests/` and `frontend/src/**/*.test.tsx` for these. No `package.json` / lockfile change.

**Not yours (Ansel, feature 039):** `backend/app/repositories/raw_fetches.py`,
`backend/app/services/fetch_persistence.py`, `backend/app/services/raw_fetch_*`,
`backend/app/db/models.py`, `backend/migrations/*`, `backend/app/main.py`,
`backend/app/config.py`, `wcl_agent/client/*`, `wcl_agent/cache/*`,
`documentation/architecture/backend-data-infra.html`. If you truly need one, post a
`question --key owner:<path>` and carry on; I arbitrate. Never commit `CLAUDE.md`, `AGENTS.md`,
`todo.md`, `.specify/memory/constitution.md` or `.specify/feature.json`.

## Done means

- All ACs met; backend suite green in a clean env; `npm run build && npm test` green.
- GitNexus impact before each symbol edit; `detect-changes --scope all --repo .` before each
  commit. Commits end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Live checks: post one board `question` with key `live-check:040` listing what team-lead should
  check on the merged branch (e.g. frame count for one tool call on anthropic; a chart survives
  reopening a chat). Team-lead batches them.
- Never push, never merge. Hand-off as your final result: branch, commits, files, test counts,
  risks, AC mapping per story, the sc-272 bypass attempt, the live-check list, and the Autonomy
  section. Update your memory at the end (light).
