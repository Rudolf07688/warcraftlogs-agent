# Brief 088a: runner fixes (fix round)

- **Branch:** `088a-runner-fixes`. **Seat:** dev-4 (Vera), fresh run. **Model:** opus medium. **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a`.
- **In parallel:** Edda (088b, frontend + ws.py), Ansel (088c, raid summary, mechanics, benchmark). Not security-core.
- **Tier S** (short plan, then implement; no Spec Kit). Fix round: fix the listed findings and nothing else (owner rule: no scope creep); anything more is a `backlog:<topic>` notice.
- **Base ref:** `sprint-2026-11-22` at BASE_SHA (all four streams merged, full suite green at f1835c4). Create your branch from it and use it as `--base`.
- **Reports** (read the cited sections, they hold file:line and the failure path): /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-22/bugs.md (BUG-001, BUG-003, BUG-007, BUG-008), /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-22/performance.md (PERF-001, PERF-007)
- One test per finding that fails before the fix; a mutation bite for any guard; `check.py run --as <you> --base BASE_SHA` on the committed head; hand-off on the board and a short result (RESULT/RECEIPT lines, one line per finding with its test).
- **Live pre-check:** if a question needs the real stack, post `live-check:088-pre` (kind `question`) with the exact command; team-lead runs it at once.

## Findings to fix
1. **BUG-001 (Medium)** `model_retry.py` ~805 `_cut_response`: a Claude call cut at 180 s after any answer text ends the turn with that text saved as a complete answer, mid-sentence, and a progress line ("Let me pull the deaths...") whose tool call was still streaming can become the whole answer. PO decision: a cut answer must never pass as complete. The user sees a plain closing line saying the answer was cut at the time limit (one fixed sentence, plain text), and the turn stats count the cut. Keep scope:084:time-cut-after-text otherwise (no re-run after answer text). If the streamed text is only progress-sized (<= the runner's INTERIM_MAX_CHARS) and no answer was kept, you may treat it like a thinking-only cut instead (one re-run): your call, post it as `scope:088a:cut-progress`.
2. **BUG-003 (Medium)** `model_retry.py` ~471: the Gemini empty-STOP re-run also fires when the turn already answered (answer text or a presenting tool result such as a chart, then an empty closing call), so the answer or chart can be repeated and a round is spent. Team-lead saw every final Gemini event carry a trailing empty text part. Re-run only when the turn has produced no answer text yet (the runner knows; pass it through TurnStats, which both files can read).
3. **PERF-001 (Medium)** 087's history breakpoint: Claude's cache look-back is about 20 blocks; a raid-overview turn is about 33 blocks (6 rounds x 2 parallel calls), so heavy chats may miss every turn start. Re-run your replay simulator (fact claude-cache-replay-sim) on a heavy fixture first and post the numbers as `measure:088a`. Fix only if a simple change within 4 breakpoints restores the reads; otherwise the numbers go on a backlog notice.
4. In-hunk Lows: **BUG-007** (`_within` drops a chunk that fully arrived past the deadline, possibly the aggregated final response with the tool calls), **BUG-008** (whitespace-only text counts as answer text and skips a due re-run), **PERF-007** (the absolute deadline counts time the consumer holds each chunk): fix if small.

## Footprint
`wcl_agent/llm/model_retry.py`, `backend/app/agent_runner.py`, new `backend/tests/test_088a_*.py`, existing `backend/tests/test_084_*.py`, `test_087_history_cache.py`, `test_079_claude_cache_budget.py`, `.claude/team/facts/`.

## Bounds
- time: the cut line is added once per cut; no extra model call for a cut after answer text.
- rate: still at most one re-run per call; the Gemini re-run never after answer text.
