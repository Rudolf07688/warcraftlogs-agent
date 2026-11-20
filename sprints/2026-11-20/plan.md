# Sprint 2026-11-20 plan (PO Maren)

Goal: the fixes from the owner's 2026-11-07 live chat. Event lookups that work, Claude turns
that are faster and always answer, a visible "thinking" line instead of silent gaps, and a
coach that explains mechanics, keeps housekeeping out of its answers and takes sensible
defaults. 22 pts, 9 stories, iteration "2026-11-20" (id 576). Base d7dab27.

## Streams (5 developers in parallel, disjoint footprints)

| # | Feature | Stories | Pts | Tier | Seat | Model | Worktree |
|---|---|---|---|---|---|---|---|
| A | 078-wcl-event-windows | sc-570 (1), sc-574 (2), sc-573 (2) | 5 | S x3, sequential | dev-2 Tomas | opus medium | dev-a |
| B | 079-claude-cache-budget | sc-568 (3), sc-567 (2) | 5 | S x2, sequential | dev-4 Vera | opus high | dev-b |
| C | 080-thinking-status | sc-569 (3), sc-572 structural | 5 | M, security-core | dev-5 Edda | opus high | dev-c |
| D | 081-boss-mechanics | sc-571 (5) | 5 | M | dev-1 Ansel | opus high | dev-d |
| E | 082-coach-defaults | sc-575 (2), sc-572 prompt line | 2 | S | dev-3 Nils | sonnet high | dev-e |

## Stories (ticket text, read once)

- sc-570 (1, bug) Event lookups with a start time always come back empty. `get_report_events`
  sends `startTime` without `endTime`; WCL returns nothing. Fix: send `endTime` whenever
  `start_time` is set; check `get_report_graph` / `get_report_table`. Tests: query variables
  carry `endTime` whenever `startTime` is set; live pre-check: page 2 of the repro returns events.
- sc-574 (2, bug) Wrong Gravebound damage figures (30.9M vs 23.6M / 21.3M). Do: 1. replay the
  turn's tool results, find the field the 30.9M came from; 2. if sc-570, close as duplicate
  after that fix and a re-run; 3. otherwise label damage fields (amount, unmitigated,
  absorbed, overkill) and add the case to the answer-judging live check (EXPECT pinned from
  `livecheck.py --facts bjXfNc92d8CPGhvB`).
- sc-573 (2, bug) Raid player list fails with a WCL "Internal server error" on Veritass's
  reports. AC: root cause stated on the ticket; if ours: participants returned, a test pins
  the query shape; if theirs: retry once, then a short typed error the agent relays in one line.
- sc-568 (3, bug) No prompt caching on the Anthropic chat path. AC: cache breakpoints (system
  + tools, growing history) so later calls read most of the prompt from cache; turn stats and
  gen_ai spans show `cache_read` > 0 from the second call; measure TTFT per call and turn cost
  before/after; Gemini unchanged.
- sc-567 (2, bug) Claude turns end "no answer" when thinking uses all 8,192 output tokens. AC:
  explicit output limit and/or capped thinking effort; a test pins the limit; on max_tokens with
  no text, retry once without thinking (or lower effort), recorded in turn stats; live: the
  trace's big multi-boss prompt answers.
- sc-569 (3, feature) Live thinking status line. AC: one-line transient status under the spell
  card from the latest thought summary (first sentence, ~80 chars), never saved, gone once the
  answer starts; new throttled stream event (~1/s) in protocol docs and frontend types;
  without summaries a generic "Thinking…" with elapsed seconds after ~3 s; plain text,
  length-capped, never markdown/HTML; Gemini and Claude.
- sc-572 (2, bug) Tool troubleshooting leaks into answers. AC: a turn with tool rounds stores
  and shows only the final answer text, interim text only as status while running; a turn
  whose tools fail says so once, plainly, no ids or retries; reload shows the same answer.
- sc-571 (5, feature) Coach explains boss mechanics (Gravebound, Ula'tek heart). AC: Gravebound
  on The Coiled Altar answers what removes a stack / what to do, with source and patch; an
  ability the guides lack gets a short "not in my guides"; live: the owner's two questions.
- sc-575 (2, feature) Too many clarifying questions. AC: the three prompts ("help me improve",
  "The ulatek heart", "is frost mage difficult?") each give an analysis with a one-line
  assumption; the agent reads stored class/spec before asking; no regression: no character
  data at all still gets one short question.

## Decisions
- One developer per shared file: model_retry.py (B), agent_runner.py + ws.py + chat frontend (C),
  agent.py instruction (E), report_tools/participants (A), kb_tools + mechanics data (D).
- sc-572 split: structural part (C), the "say it once, plainly" prompt line (E).
- sc-571: curated mechanic notes in the repo + a lookup tool in the KB tool group, no migration.
- Prompt budget split (test_064): D +400, E +250, A +100, C +50, B 0 tokens.
- No scrum master: no shared file, no migration.

## Drop first
sc-575 (E) and the generic-"Thinking…" fallback; then sc-574 if it closes with sc-570.
