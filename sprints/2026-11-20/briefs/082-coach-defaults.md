# Brief 082-coach-defaults (dev-3 Nils)

- **Feature / branch:** 082 / `082-coach-defaults`
- **Tier:** S: a short plan, then implement. No Spec Kit.
- **Model / effort:** sonnet, high
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-e` (detached at the base). **Base ref:** `d7dab27`.
- **Seat:** dev-3 (Nils). In parallel: Tomas (078, WCL tools), Vera (079, Anthropic request; she must not touch `agent.py`), Edda (080, status line + stored answer), Ansel (081, boss-mechanics tool).
- **Security-core:** no. **Migration:** none.
- You own `wcl_agent/agent.py` this sprint (the instruction body). Change only the instruction text and what 575 needs; leave `TOOL_GROUPS`, `build_agent` and `build_instruction`'s time block alone unless a blocker from Vera says otherwise.

## Stories (acceptance criteria verbatim)

### sc-575 (2 pts, feature): Coach asks too many clarifying questions instead of taking a sensible default
Three of six answers in the owner's 2026-11-07 chat led with questions where a default would have served:
- "help me improve" → three numbered questions (which character, which run, what goal). The owner answered "in general".
- "The ulatek heart" → a menu of three options, no analysis.
- "is frost mage difficult?" → "I need to confirm that Traecie is a Frost Mage and not a Frost Death Knight", although her class is stored (raid summary and profile settings know Mage since the 11-07b fix).
**Goal.** Act on the most likely reading and say so in one line ("I took your newest kill on Ula'tek and looked at the Heart phase; tell me if you meant something else"). Ask first only when the readings lead to different costly work and nothing in the profile, stored reports or the chat picks one.
**Acceptance.**
- The three prompts above (same account) each produce an analysis with a one-line assumption, not a question list.
- The agent reads the stored class/spec (main_class/main_spec, stored rankings) before asking about a character's class.
- No regression: a question with no character data at all still gets one short question.

### sc-572 (2 pts, bug), prompt part (decision:572-split)
Your AC: **A turn whose tools fail says so once, plainly, in the answer ("Warcraft Logs failed on the player list, so I used her rankings instead"), with no ids or retries.** Write it in `<TOOL_FAILURES>`. The structural part (interim text as status, stored answer = final text) is Edda's (080). Don't move sc-572 on Shortcut; I do once both halves are merged.

## PO notes
- Today's instruction pushes the other way in several places: `<EVIDENCE_CONTRACT>` 4 ("ask for the smallest missing input"), `<CONTEXT_RESOLUTION>` ("If an omitted value … could change a report-specific answer, ask one concise question"), `<RUN_RESOLUTION>` 4 (always ask which run, decision D5, pinned by `test_run_resolution_follows_decision_d5`). Reconcile them into one rule rather than adding a contradicting one. D5 exists because a wrong run puts the wrong people into a profile: keep the ask for profile-writing actions; record your reconciliation as `scope:082:defaults`.
- Check what KNOWN PLAYER CONTEXT (`profile_context.py`) actually carries for the user's own characters and friends: `class_name`/`active_spec`, and since 11-07b `main_class`/`main_spec` on the profile. Traecie's class was stored but the agent still asked: find out why (not in the block, or the prompt doesn't tell it to trust the block) and fix the cause.
- `contract:mechanics-tool`: point `<ANALYSIS_ROUTING>`'s "External mechanics question" line at `get_boss_mechanics` (Ansel builds it; your base lacks it, the name is the contract). Your consumer test: that line names the tool.
- Prompt-wording pin tests are not wanted (developer.md), except where a pinned clause already exists and you change it: update that pin. The prompt-size test stays: your share is +250 tokens (contract:prompt-budget; `python3 .claude/team/tokens.py`).
- The time block stays last (`test_time_block_is_last_so_the_prefix_stays_cacheable`): Vera's caching depends on it.

## Answer quality (live pass)
Post EXPECT entries under `live-check:082` for the three prompts (same account as the owner) and the no-character-data case, pinned to facts, not wording: e.g. "the answer contains no more than one question mark before the first analysis heading", "a tool call was made in the turn", "the answer names Mage for Traecie", the stored class from `livecheck.py --facts`. Team-lead runs them at the tip.

## File footprint (board `owner:` keys, to nils)
- `wcl_agent/agent.py`, `backend/app/services/profile_context.py`
- `backend/tests/test_prompt_contract.py`, `backend/tests/test_profile_context.py`, new `backend/tests/test_082_*.py`
A prompt pin elsewhere you must update (test_046_compact_tables, test_046_search_data, test_050_*, test_kb_search_prompt, test_kb_eval, test_profile_tools): post a blocker naming it and I grant it at once.

## Live pre-check
If a question needs the real stack, post `live-check:082-pre` with the exact command while building; team-lead runs it at once. Never call a real model or read `.env` yourself.

## Stories on Shortcut
Move sc-575 to In Progress when you start, Under Review in your hand-off.

## Known facts
- **wcl-agent-no-backend-imports**: `wcl_agent` never imports `backend`; shared helpers move into `wcl_agent`.
- **tool-docstring-is-prompt**: prompt text is pinned verbatim, some pins across line breaks, in backend/tests/test_{prompt_contract, 046_compact_tables, 046_search_data, 050_report_fights, 050_kickoff_overview, kb_search_prompt, kb_eval, profile_tools}.py; test_064 caps instruction plus schemas.
- **runner-outcome-flag-on-record**: `ws.py` calls `profile_context.build_preamble`; outcome flags travel on the yielded record, never by matching text.
- **ws-refresh-actor-patch-signature**: ws tests patch `ws_mod.set_refresh_actor` with `lambda *_: None`; don't add a keyword argument at its call site (ws.py is Edda's anyway).
- **ws-test-helpers**: reuse the helpers in `backend/tests/test_proposal_ws.py` for any WebSocket test.
- **pg-tests-shared-db**: Postgres tests share one DB; unique data, no exact global lists.
