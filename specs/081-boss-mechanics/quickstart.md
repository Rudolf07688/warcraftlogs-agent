# Quickstart

- Tests: `python3 .claude/team/check.py run backend/tests/test_081_boss_mechanics.py --as <you>`.
- Try it: `uv run python -c "import asyncio; from backend.app.agent_tools.mechanics import get_boss_mechanics as g; print(asyncio.run(g('The ulatek heart')))"`.
- New tier: add `<tier>.json` beside `venomous_abyss.json` (ids from the Encounter Journal, see `live_pre.py`), run
  the tests (key uniqueness, sources), and update `test_notes_load_only_from_the_fixed_data_directory`.
