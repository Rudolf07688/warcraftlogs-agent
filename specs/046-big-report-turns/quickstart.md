# Quickstart: verify 046

- `python3 .claude/team/check.py run backend/tests/test_046_compact_tables.py backend/tests/test_046_empty_turn.py backend/tests/test_046_search_data.py backend/tests/test_046_kickoff_prefetch.py --as nils`
- Full suite: `python3 .claude/team/check.py run --as nils`
- Live (team-lead): click a recent 20-player Heroic raid; ask "top 5 damage on the <boss> kill"; check the `turn stats` line: `max_prompt_tokens` < ~40k, `tool_calls` small, no per-player `get_report_table(source_id=…)` calls.
