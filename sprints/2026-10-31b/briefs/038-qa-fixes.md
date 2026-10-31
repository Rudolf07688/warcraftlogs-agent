# Brief 038: QA sweep fixes (crucial only)

- **Branch:** `038-qa-fixes`, cut from the sprint tip `sprint-2026-10-31b` (bedc273 or later), in
  `/home/rudolf/dev/wcl-worktrees/dev-b`: `git switch -c 038-qa-fixes sprint-2026-10-31b`.
- **Tier:** S. **Seat:** dev-2 (Tomas): all these findings are in 037 code you wrote.
- **Reports:** `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-10-31b/` (bugs.md,
  performance.md, security.md). Read the finding before you fix it.
- **No new stories.** These are rework on sc-157, sc-158, sc-176/184 and sc-179, all of them Under
  Review already. Mention the QA ID in each commit message.
- **Autonomy:** the same as in your 037 brief. Decide, and post each decision with its reason.

## Fix these (and nothing else)

1. **BUG-001 (High), sc-157.** Remote images get past the block through
   `<picture><source srcset>`. Strip `srcset`/`source` (or `picture`) after sanitize in
   `StreamMarkdown.tsx`. While you're in there, tighten `allowedProtocols` so the protection
   doesn't depend on plugin order (SEC note in security.md). Add a test with the exact payload.
2. **BUG-002 (Medium), sc-176.** A retry-disabled call (the greeting, `retry=False`) poisons the
   5-minute 429 memory. Remember a model only when its retries really ran out on a chat turn.
   Add a test.
3. **PERF-001 (High), sc-176/184.** The web-search sub-agent (`may_switch=False`) waits through
   the full retry schedule and never remembers the limit. Give it the short budget and remember
   the limit, consistent with fix 2. Update `test_web_search_fallback.py:99`.
4. **BUG-003 + SEC-002 (Low), sc-158.** In `client_source`:
   - strip `:port` and `[v6]:port` from hops before parsing;
   - normalise IPv4-mapped addresses for the peer and for the hops;
   - when every hop is trusted, key on the peer or the rightmost hop, never `hops[0]`;
   - change the `.env.example` wording to recommend the exact proxy address or network, not
     `/12`.

   Leave `docker-compose.yml` alone; that goes to the backlog. Add tests.
5. **SEC-003 (Low), sc-179.** Nested closing tags get past the title prompt delimiting. Strip
   repeatedly until the text is stable, or escape `<` and `>`. Add a test.

**Not in scope** (I'm putting these on the backlog): PERF-002 (both models remembered),
security SEC-001 (`ws.py` `str(exc)`), the realm prose limit, BUG-004/005, docs drift, and the
compose port.

## Footprint

`frontend/src/components/StreamMarkdown.tsx` and its test, `wcl_agent/llm/model_retry.py`,
`wcl_agent/agent.py`, `backend/app/auth/rate_limit.py`, `backend/app/config.py`, `.env.example`,
`backend/app/services/conversation_titles.py`, and the tests for these.

## Done means

- The backend passes `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`, and the
  frontend build and tests pass.
- Run detect-changes before each commit. End commit messages with
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Never push.
- Hand off as your final result: the branch, commits, a fix-to-finding mapping, and the test
  counts.
