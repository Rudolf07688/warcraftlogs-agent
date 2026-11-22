# Quickstart: verify 085

```bash
W=/home/rudolf/dev/wcl-worktrees/dev-b
python3 $W/.claude/team/check.py run backend/tests/test_085_status_frames.py backend/tests/test_080_thinking_ws.py backend/tests/test_082b_preamble_main.py --as edda
python3 $W/.claude/team/pg.py up edda   # then with TEST_DATABASE_URL:
python3 $W/.claude/team/check.py run backend/tests/test_085_main_selection_pg.py --pg edda --as edda
python3 $W/.claude/team/check.py run frontend/src/App.thinking.test.tsx --as edda
```

Live (team-lead, at the tip): ask a question that makes tool calls; the thinking line shows under the cards and the answer completes; reopen the chat and compare with the live view.
