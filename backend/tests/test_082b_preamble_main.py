"""082b: the turn preamble carries the workspace's saved main class/spec (sc-575)."""

from backend.app.api import ws
from backend.app.db import repository as repo


async def test_saved_main_reaches_the_turn_preamble(session, tenant_id):
    await repo.set_main_selection(
        session, tenant_id=tenant_id, main_class="Paladin", main_spec="Holy", main_content=None
    )
    await session.commit()
    preamble = await ws._build_turn_preamble(session, tenant_id, "how did I do?")
    assert "Paladin" in preamble and "Holy" in preamble


async def test_no_settings_row_leaves_the_preamble_unchanged(session, tenant_id):
    preamble = await ws._build_turn_preamble(session, tenant_id, "how did I do?")
    assert preamble == ""
