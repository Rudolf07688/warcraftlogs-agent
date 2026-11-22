# Brief 088b: status UI and drop recheck fixes (fix round)

- **Branch:** `088b-status-ui-fixes`. **Seat:** dev-5 (Edda), fresh run. **Model:** opus medium. **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-b`.
- **In parallel:** Vera (088a, model_retry.py + agent_runner.py), Ansel (088c). D18-reviewed area: keep the 085 guarantees (stored == shown, plain status text).
- **Tier S** (short plan, then implement; no Spec Kit). Fix round: fix the listed findings and nothing else (owner rule: no scope creep); anything more is a `backlog:<topic>` notice.
- **Base ref:** `sprint-2026-11-22` at 39c4b3f (all four streams merged, full suite green at f1835c4). Create your branch from it and use it as `--base`.
- **Reports** (read the cited sections, they hold file:line and the failure path): /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-22/spec-conformance.md (SPEC-001, SPEC-002, SPEC-004), /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-22/bugs.md (BUG-004..006), /home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-22/performance.md (PERF-003, PERF-004)
- One test per finding that fails before the fix; a mutation bite for any guard; `check.py run --as <you> --base 39c4b3f` on the committed head; hand-off on the board and a short result (RESULT/RECEIPT lines, one line per finding with its test).
- **Live pre-check:** if a question needs the real stack, post `live-check:088-pre` (kind `question`) with the exact command; team-lead runs it at once.

## Findings to fix
1. **SPEC-001 = BUG-006 (Medium)**: the drop rechecks end after about 62 s (2+4+8+16+32), but the server notices a drop only at its next send, which can come after a 180 s Claude call plus a 180 s re-run plus rate-limit waits. The tab then keeps the retracted text as the answer, against spec 085 FR (the browser never keeps its local copy when the server saves one). Cover the server's worst case: PO bound: rechecks continue up to **8 minutes** after the drop with growing gaps (at most about 10 fetches), and stop as soon as the server has a saved agent message for that turn.
2. **PERF-003 (Medium)**: each recheck refetches the whole chat and replaces every message, re-rendering every chart. Only update when the fetched chat differs from what is shown (e.g. compare the last message id/seq), and don't touch unchanged messages.
3. **SPEC-002 (Medium)** `MessageList.tsx` ~134: the retry/fallback notice shows only while no answer text is on screen, so a rate-limit wait in a later round (after text was kept) is a silent stall. Show the notice while text is showing too (plain, clamped, as under the cards), cleared by the next frame as today.
4. In-hunk Lows: **BUG-004** (reopening the same chat doesn't cancel a pending recheck, which re-adds the local copy), **BUG-005** (one failed recheck fetch ends the rechecks silently), **PERF-004** (a pending recheck is not cancelled on a new turn or chat switch), **SPEC-004** (`ws.py` `_retry_frame` guards wait_s but not attempt/max_attempts as finite numbers).

## Footprint
`frontend/src/**`, `backend/app/api/ws.py` (`_retry_frame` only), new `backend/tests/test_088b_*.py`, existing `backend/tests/test_085_status_frames.py`, `.claude/team/facts/`.

## Bounds
- rate/time: at most ~10 recheck fetches per drop within 8 minutes, one chain at a time; cancelled on chat switch, reopen and new turn (test each).
- size: no re-render of unchanged messages (test a chart message renders once across rechecks).
