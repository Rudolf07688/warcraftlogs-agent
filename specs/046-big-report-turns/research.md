# Research: 046 big-report turns

## R1 Table cap and projection (sc-334)
- Decision: table-only cap `TABLE_MAX_CHARS = 40_000` (10k tokens at chars/4). Over it, `compact_table` walks `table["data"]`: scalars kept; each list of dicts becomes its top 25 rows (sorted by `total`, else `totalUptime`, else original order) with `<list>_omitted`; a dict of lists (Summary `playerDetails`) is walked one level down. Rows keep scalar fields only; `icon` "Class-Spec" becomes `class`/`spec` when it starts with the row's `type`; a nested dict with a `name` keeps that name (death `ability`); nested lists (abilities, targets, gear, talents, events) are dropped. 048 (QA BUG-003): a row's `entries`/`details` lists are its own rows (Interrupts: wrapper → spells → players; Dispels likewise), so they are cut to top-N recursively with `<list>_omitted`, and their omitted rows count toward `_truncated`. `per_second = total / (totalTime / 1000)` when both exist. If still over the cap: 10, then 5 rows; else note only.
- Rationale: one generic function covers DamageDone/Healing/Casts/DamageTaken/Deaths/Buffs/Summary and per-source tables without a per-type table of fields; the bloat is in nested lists.
- Alternatives: per-data-type projections (more code, same result); lowering `MAX_JSON_CHARS` for all tools (AC4 forbids).
- Completeness: `_truncated` only when rows were omitted (board clarify:046-completeness).

## R2 Empty final answer (sc-302)
- Decision: `_run_turn` tracks whether answer text arrived after the last tool result; at the end, with no pending call, a chat turn (workspace `user_id`) yields `EMPTY_ANSWER_MESSAGE` as the closing token and sets `stats.outcome = "empty"`; `stream_response` keeps that outcome. Text after a tool round that follows earlier text gets a `\n\n` prefix. `tool_calls` counted from `tool_start` records in `stream_response`.
- Rationale: no `ws.py` change; ws already saves tokens as the agent message.
- Alternatives: a flag passed by ws.py (Ansel's file this sprint) — backlog item for an explicit parameter.
- 048 (QA BUG-002): the closing token carries `"empty": True`; ws.py pops it, still saves the message, and skips `offer_exchange`, `schedule_title` and follow-ups for that turn (the chat keeps `title_source=auto`, so its next answer names it).

## R3 Data delimiters (sc-328)
- Decision: `payload()` wraps each hit text as `<data>…</data>` after replacing `<`/`>` with `‹`/`›`. Instruction EVIDENCE_CONTRACT 5 names the rule; `UNTRUSTED_NOTE` too. Chunker caps: title 80, guild 40 (`bounded`).

## R4 Kickoff pre-fetch (sc-339)
- Decision: `kickoff_prefetch.schedule(identity, code)` → `background.spawn(prefetch(...), ("kickoff_prefetch", tenant_id, code))`. Inside: set `current_identity`, `load_report_summary(code)`, pick bosses, `asyncio.gather(get_report_table(code, "Summary", fight_id=f) …)` (≤10). Exceptions logged. Scheduled only when `app.state.fetch_writer` is set.
- As built (P7-046 SEC-001/002, QA 048): `schedule` gates on `settings.wcl_store_reads_enabled` and `wcl_client._fetch_source` (no store reads → nothing for the turn to read), and keeps a per-(workspace, report) cooldown of 600 s from the job's start, in-process. The boss tables run inside `background_lane()`. QA PERF-001: the turn's identical queries join those flights, so they waited on the 2-slot background lane; now each client single-flight carries a `LaneTicket`, and an interactive caller that joins promotes it (`LaneLimiter.promote`: a queued ticket is served by the interactive rule, a held background slot stops counting against the cap). The summary goes through the cache-level single-flight, which a joiner can't promote, so it is loaded in the interactive lane: one request, the same one the turn sends first.
- Rationale: identical tool calls → identical query keys → the turn's calls are store/single-flight hits; identity = the workspace that already passed the 404 rule, so grants equal what its own turn would get.
- Alternatives: injecting data into the turn (touches ws.py, puts WCL text in the prompt) — rejected per brief.

## R5 Fixture
- Synthetic, deterministic 20-player Heroic kill DamageDone + Summary tables in the documented WCL shape (009 research R3 facts; chunker shapes), with gear/talents/abilities/targets so it exceeds the cap like the live table. No live access in development; the live pass checks real data.

## R6 Impact
- `_acap` CRITICAL (15 callers) — not edited. `get_report_table`, `get_stored_fight_table` UNKNOWN (registered as tools): text search shows only tool registration, `tool_summary`, `raids` capture (reads `status`/args) and tests. `payload`, `stream_response`, `_run_turn`, `investigate_raid`, `_summary_chunks` checked before edit.
