# Brief 042: QA fixes for 040 (sc-213, sc-140), one round

- **Branch:** `042-qa-chat-fixes` from the sprint tip:
  `git -C /home/rudolf/dev/wcl-worktrees/dev-b switch -c 042-qa-chat-fixes sprint-2026-10-31c`
  (tip `5550997`, which already has 039 and 040 merged).
- **Tier:** S. Seat `dev-2` (Tomas), the author of 040.
- **Reports:** `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-10-31c/spec-conformance.md`
  (SPEC-002) and `bugs.md` (BUG-006).
- **Footprint:** `backend/app/api/ws.py`, `frontend/src/**`, tests for these. You may also call
  existing helpers in `backend/app/db/repository.py` (e.g. `assign_message_seq_to_turn_captures`)
  and make a small change there if one is needed. It's free this round; post `owner:` first if
  you do. Don't touch Ansel's 039 files (`owner:039`).
- **Parallel:** Ansel fixes the raw-store findings in dev-a.
- **Tests:** `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`;
  `cd frontend && npm run build && npm test`. Check out `frontend/tsconfig.tsbuildinfo` before
  you commit. Make the build a hard gate before `git commit` (your own lesson).

This is the one rework round. Fix exactly these two; anything else goes on the board as
`backlog:<topic>`.

## Fix 1 (sc-213, SPEC-002): charts from an interrupted turn vanish on reload
The QA auditor found a real root cause:
- Captures are linked to a message only after a completed turn (`ws.py:376`).
- The disconnect path (a page reload mid-answer) and the generic error path save a partial
  message through `_persist_partial`, but never link the turn's captures. The `ModelRateLimited`
  path saves no message at all.
- Artifacts are created with `message_seq=None`, and `restClient.ts:230` drops those on reload.
  The next completed turn then claims the orphans, so the chart reappears under a later,
  unrelated answer.

Acceptance criteria:
1. A chart from a turn that ends in an error, a rate limit or a disconnect is linked to that
   turn's message (the partial agent message, or a sensible anchor when no agent message is
   saved; post your rule), and renders there after a reload.
2. A later turn never claims an earlier turn's charts.
3. Tests: the disconnect, error and rate-limit paths each link their captures, and a following
   completed turn doesn't steal them.
4. Name this root cause in the hand-off. sc-213 stays Under Review; the owner's live check
   decides.

## Fix 2 (sc-140, BUG-006): scroll-to-question releases the stick-to-bottom lock
`stopScroll()` on completion leaves `escapedFromLock` set, so the next turn isn't followed and
`following` reads false.

Acceptance criteria:
1. When a new turn starts (the user sends, or clicks a suggestion), the view follows the stream
   again, as it did before sc-140.
2. sc-140's own behaviour is unchanged: scroll to the question on completion, only if the user
   was following, and no jump on reopen.
3. A test: a completed turn, then a new turn that is followed (the lock re-engaged).

## Done means
- All ACs met, backend and frontend suites green, GitNexus impact before each edit,
  `detect-changes` before each commit. Commits end with
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Don't move tickets (they stay Under Review). Never push or merge.
- Hand-off: branch, commits, files, test counts, an AC mapping per fix, and the sc-213 root cause.
