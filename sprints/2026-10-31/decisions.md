# Sprint 2026-10-31 decisions (product owner)

Decisions marked **(owner review)** were the PO's recommendations for the owner's single plan
review. **Owner GO (2026-10-31, via team-lead): "go". D0–D3 are accepted as recommended.**

## D0 — 2026-10-31: Sprint scope
- **Question:** What does this sprint deliver?
- **Answer:** Epic 248 (switchable LLM provider: sc-249, sc-250, sc-251, sc-252, sc-253,
  14 points), plus the crucial epic-203 QA fixes sc-241, sc-242 and sc-243 (6 points)
  and sc-159 (1 point, same discovery function as sc-250). 21 points in features 032–035.
  sc-221 heads the next sprint (Priority High).
- **Why:** Provider switching is the owner's first priority. sc-241..243 were flagged
  "fix first next sprint". sc-221 (3) would take the sprint to 24, over the range. It is
  additive hardening, so doing it next sprint doesn't increase the cost of change.

## D1 — 2026-10-31: How the provider is switched (owner review)
- **Question:** Config only, a runtime toggle in the UI, or both providers live at once?
- **Recommendation:** **Config only**: `WCL_LLM_PROVIDER=vertex|anthropic` in `.env` plus
  a restart, with a read-only provider label in the model picker (sc-251).
- **Alternatives:**
  (a) An admin-only runtime toggle in the UI: it needs re-discovery at runtime, a
      runner-cache reset and a stored setting. About +5 points, filed as a follow-up if
      wanted.
  (b) Both providers live at once, with the picker listing "Claude … · Anthropic API"
      next to the Vertex models and each chat choosing. About +3 points, and it needs a
      "primary provider" rule for background calls anyway.
- **Why:** Every model setting today already needs a restart (runners are cached per
  model, discovery runs at startup). One line plus a restart is simple and safe. The
  provider layer from 032 keeps (a) and (b) cheap later.

- **Owner confirmed (2026-10-31, via team-lead):** accepted as recommended.

## D2 — 2026-10-31: What "anthropic" covers (owner review)
- **Question:** Does `anthropic` move only the chat, or every LLM call?
- **Recommendation:** **Every LLM call**: the chat agent, greeting, suggestions, titles,
  report synthesis and the guide pipeline. Gemini is not offered under `anthropic`.
  Google ADC is then not needed for LLM calls. WCL and Blizzard APIs are unaffected.
- **Why:** One switch, one provider, no surprise Vertex calls (or charges) after a switch.
  A Claude-only mixed mode would need per-call-site rules (constitution I, III).

- **Owner confirmed (2026-10-31, via team-lead):** accepted as recommended.

## D3 — 2026-10-31: Web search under the Anthropic API (owner review)
- **Question:** Does the chat get web search on Claude, and how do guides stay grounded?
- **Recommendation:** The **chat keeps today's Claude behaviour** (no web search; the
  capability summary already says so), and adding Anthropic web search to the chat is a
  follow-up story. The **guide pipeline uses Anthropic's server-side web search tool**
  (sc-253), so guides stay grounded and cited. The owner must enable web search in the
  Anthropic Console; searches are billed per use.
- **Why:** Guides fail without grounding, so it is in scope. Chat web search on Claude was
  never there, so adding it would be new scope.

- **Owner confirmed (2026-10-31, via team-lead):** accepted as recommended.

## D4 — 2026-10-31: Chats created under the other provider
- **Question:** What happens to a chat whose stored model isn't served after a switch?
- **Answer:** It continues on the active provider's default model, with no error and no
  migration of stored ids.
- **Why:** Simplest behaviour that never strands a chat.

## D5 — 2026-10-31: Model roles per provider
- **Question:** How do the fixed models (report, guide, guide review, suggest, greeting,
  default chat) map across providers?
- **Answer:** Each role has a per-provider default (Claude ids per the `claude-api` skill:
  a fast model for suggestions, titles and greeting; a mid model for reports and guide
  authoring; a stronger, different model for guide review). An explicit env value wins.
- **Why:** The owner switches one line, not six. Existing env overrides keep working.

## D6 — 2026-10-31: No separate design/spike story
- **Question:** Is a design doc or spike needed first, as for epic 203?
- **Answer:** No. 032's Spec Kit plan publishes the provider-layer contract early (via
  the scrum master), and 035 specifies against it. This is the same pattern as 027's
  shared proposal contract.
- **Why:** The change is a well-bounded seam (`wcl_agent/llm/vertex.py` already builds
  every client). A separate doc would duplicate 032's plan (constitution I, III).

## D7 — 2026-10-31: Iteration
- **Question:** Which Shortcut iteration holds the sprint?
- **Answer:** The new iteration "Sprint 2026-10-31" (id 254, 2026-10-31 → 2026-11-13), as
  the owner asked ("add it as the next sprint"). Sprint stories move to Shortlist in it.
  The long-running "WCL App Q4 2026" (161) keeps the earlier sprints' stories.

## D8 — 2026-10-31: 034 spec interpretations (sc-241, sc-242)
- **Question:** sc-241 AC 1 expects "2 skipped, 1 valid" for realm None + played_role
  "Healer" + 1 valid, but the same AC makes roles case-insensitive, so "Healer" is valid.
  How do unknown roles behave, and where does the sc-242 race test run?
- **Answer:** Accepted as signed off by the scrum master. The acceptance test is a
  superset: realm null (`invalid_realm`), region "" (`invalid_region`), action "promote"
  (`invalid_item`), played_role "Healer" (valid, stored as `healer`) and one fully valid
  item give 3 skipped + 2 valid, with no `agent_error`. An unknown `played_role`
  (display-only) is dropped and the item stays valid. An unknown `raid_role` skips the item
  as `invalid_item`. The sc-242 race test runs against real Postgres (it skips itself
  without `TEST_DATABASE_URL`; the developer pastes the run into the hand-off), plus a
  SQLite unit test.
- **Why:** It matches the ticket's intent (bad rows are skipped, good rows survive, no crash)
  and stays consistent with case-insensitive roles.
- **Out of scope:** two different proposals in one chat decided at the same instant can
  collide on the message seq (max+1 in `_next_seq`). This pattern predates the sprint and
  is not sc-242. Filed as sc-255 (Backlog, bug, 2 points, Low), not added to 034.

## D9 — 2026-10-31: 032 clarify (default chat model under `anthropic`, role overrides, Claude thinking fix)
- **Q1 — default chat model under `anthropic`:** **claude-sonnet-5-5**. It has the right cost
  and latency for a tool-heavy chat. Opus and Haiku stay selectable in the picker. With D5
  this gives: default chat, report and guide author → claude-sonnet-5-5; guide review →
  claude-opus-5-5; suggest/fast and greeting → claude-haiku-5-5. Vertex defaults are
  unchanged.
- **FYI-1 (accepted):** an explicit role env value that the active provider can't serve
  (e.g. a Gemini id under `anthropic`) is ignored with one warning per role, and the
  provider default is used. A Claude id set explicitly still wins. This keeps D1's
  "one line" switch true with the owner's current `.env`.
- **FYI-2 (accepted, in scope):** ADK 2.10's Anthropic adapter rejects the planner's
  ThinkingConfig without a budget, so Claude agent turns fail today on both providers. 032
  switches Claude to adaptive thinking and sends the thinking-block mismatch control, so
  trimmed history doesn't return a 400. AC3 needs both to pass live, they stay in 032's own
  files, and Claude-on-Vertex working again is a side effect, not new scope.
- **`WCL_GREETING_MODEL` (accepted):** needed for AC7 (the greeting role).
- **REST create keeps a 400 for unknown ids (accepted, with a condition):** after a switch,
  the frontend must not send a stale model id that is no longer served. If the saved picker
  selection isn't in `/api/models`, it falls back to the default. This is AC6's intent
  ("no error after a switch") applied to new chats. If the frontend already does this, a
  test is enough; if not, it is a one-line fix inside 032.

## D10 — 2026-10-31: Owner GO on the plan review
- **Question:** Does the owner approve the high-level plan (owner gate)?
- **Answer:** Yes. The owner replied "go" (relayed by team-lead), accepting all four
  recommendations: D1 (config plus restart, read-only provider label), D2 (`anthropic`
  covers every LLM call), D3 (chat without web search; guides use Anthropic web search),
  and D0 (scope: sc-249..253, sc-241/242/243, sc-159; sc-221 heads the next sprint). The D9
  model defaults stand.
- **Effect:** Implementation may proceed after each feature's Spec Kit gates (scrum-master
  sign-off). There are no more owner gates; the team runs autonomously to delivery.
