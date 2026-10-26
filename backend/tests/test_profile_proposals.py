"""Profile change proposals (feature 029 / sc-205): storage, validation, execution, tenancy.

Design: documentation/designs/self-aware-agent/capabilities-and-tools.html (C8–C14).
SQLite by default; the Postgres-only RLS checks follow test_rls.py and are skipped without
``TEST_DATABASE_URL``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from backend.app.db import repository as repo
from backend.app.db.models import UserCharacter


# --- Migration 0016 (AC 7) ------------------------------------------------------


def test_migration_0016_upgrades_and_downgrades():
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0016_profile_proposals.py"
    spec = importlib.util.spec_from_file_location("migration_0016", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.revision == "0016_profile_proposals"
    assert mig.down_revision == "0015_rescan_mplus_runs"

    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        for table in ("tenants", "users", "conversations"):
            conn.execute(sa.text(f"CREATE TABLE {table} (id VARCHAR(36) PRIMARY KEY)"))
        with Operations.context(MigrationContext.configure(conn)):
            mig.upgrade()
            inspector = sa.inspect(conn)
            assert "profile_proposals" in inspector.get_table_names()
            columns = {c["name"] for c in inspector.get_columns("profile_proposals")}
            assert columns == {
                "id", "tenant_id", "user_id", "conversation_id", "message_seq", "status",
                "items", "created_at", "expires_at", "applied_at",
            }
            assert [i["name"] for i in inspector.get_indexes("profile_proposals")] == [
                "ix_profile_proposals_tenant_conversation"
            ]
            mig.downgrade()
        assert "profile_proposals" not in sa.inspect(conn).get_table_names()


# --- One write path: friend cap (D8) and realm-slug duplicates (C12) over REST ----


@pytest.fixture
def no_guide_tasks(monkeypatch):
    # Adds start a background guide task that would hit WCL / the model.
    monkeypatch.setattr("backend.app.api.profile.schedule_character_guide", lambda *_: None)


async def _seed_friends(patched_db, tenant_id, count: int) -> None:
    async with patched_db() as db:
        for i in range(count):
            db.add(UserCharacter(tenant_id=tenant_id, role="friend", name=f"Pal{chr(97 + i % 26)}{i}", server="S", region="EU"))
        await db.commit()


async def test_rest_friend_add_stops_at_the_cap(as_user, patched_db, no_guide_tasks):
    await _seed_friends(patched_db, as_user.tenant_id, repo.MAX_FRIENDS - 1)
    body = {"server": "Tarren Mill", "region": "EU"}
    ok = await as_user.client.post("/api/profile/friends", json={**body, "name": "Last"})
    assert ok.status_code == 201, ok.text
    refused = await as_user.client.post("/api/profile/friends", json={**body, "name": "OneTooMany"})
    assert refused.status_code == 409 and refused.json()["detail"] == "friend_limit"


async def test_profile_over_the_cap_keeps_every_friend(as_user, patched_db, no_guide_tasks):
    await _seed_friends(patched_db, as_user.tenant_id, repo.MAX_FRIENDS + 2)
    profile = (await as_user.client.get("/api/profile")).json()
    assert len(profile["friends"]) == repo.MAX_FRIENDS + 2  # nothing is trimmed
    refused = await as_user.client.post(
        "/api/profile/friends", json={"name": "Extra", "server": "S", "region": "EU"}
    )
    assert refused.status_code == 409 and refused.json()["detail"] == "friend_limit"
    # Own characters have their own limit, so they are unaffected.
    own = await as_user.client.post(
        "/api/profile/self", json={"name": "Mine", "server": "S", "region": "EU"}
    )
    assert own.status_code == 201


@pytest.mark.parametrize(
    ("first", "second"),
    [("Tarren Mill", "tarren-mill"), ("Kel'Thuzad", "kelthuzad"), (" Area 52 ", "area-52")],
)
async def test_rest_realm_spellings_are_one_realm(as_user, no_guide_tasks, first, second):
    r = await as_user.client.post(
        "/api/profile/friends", json={"name": "Jaina", "server": first, "region": "EU"}
    )
    assert r.status_code == 201
    dup = await as_user.client.post(
        "/api/profile/friends", json={"name": "jaina", "server": second, "region": "eu"}
    )
    assert dup.status_code == 409 and dup.json()["detail"] == "duplicate_friend"
    # The stored realm keeps the spelling it was entered with.
    assert (await as_user.client.get("/api/profile")).json()["friends"][0]["server"] == first
