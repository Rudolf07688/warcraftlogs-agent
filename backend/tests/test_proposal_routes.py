"""Approve / cancel routes for agent profile proposals (feature 031 / sc-207 AC 2, 4, 5).

Design: participants-and-confirmation.html #transport (REST table) and #followup. The routes
call only feature 029's proposal service; these tests drive them over HTTP on the SQLite
fixtures and check the profile, the saved follow-up line and the error codes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from backend.app.api import proposals as routes
from backend.app.db import repository as repo
from backend.app.schemas import ProfileChangeIn, ProfileProposalOut
from backend.app.services import profile_proposals as proposals
from backend.app.tenancy.context import RequestIdentity


def _identity(authed) -> RequestIdentity:
    return RequestIdentity(
        user_id=authed.user_id,
        tenant_id=authed.tenant_id,
        membership_role="tenant_admin",
        is_platform_admin=False,
        session_id=uuid.uuid4(),
    )


def _add(name: str, **kw) -> ProfileChangeIn:
    return ProfileChangeIn(action="add", target="friend", name=name, realm="Tarren Mill", region="eu", **kw)


@pytest.fixture(autouse=True)
def no_guide_tasks(monkeypatch):
    # An applied add starts a background guide task that would hit WCL / the model.
    monkeypatch.setattr(proposals, "schedule_character_guide", lambda *_: None)


@pytest.fixture
async def conv(as_user, patched_db) -> uuid.UUID:
    async with patched_db() as db:
        conversation = await repo.create_conversation(db, "gemini-3.6-flash", tenant_id=as_user.tenant_id)
        await db.commit()
        return conversation.id


@pytest.fixture
async def proposal(as_user, patched_db, conv):
    """Kazrok and Brightmane are new; Nightpaw is already a friend (skipped)."""
    async with patched_db() as db:
        await repo.add_character(
            db, tenant_id=as_user.tenant_id, role="friend", name="Nightpaw", server="Tarren Mill", region="EU"
        )
        await db.commit()
    return await proposals.create_proposal(
        _identity(as_user), conv, [_add("Kazrok"), _add("Brightmane"), _add("Nightpaw")]
    )


async def _friends(client) -> list[str]:
    return sorted(f["name"] for f in (await client.get("/api/profile")).json()["friends"])


async def _agent_lines(patched_db, conv, tenant_id) -> list[str]:
    async with patched_db() as db:
        return [m.content for m in await repo.list_messages(db, conv, tenant_id=tenant_id) if m.role == "agent"]


def _expire(monkeypatch) -> None:
    later = datetime.now(UTC) + proposals.PROPOSAL_TTL + timedelta(minutes=1)
    monkeypatch.setattr(proposals, "_now", lambda: later)


async def test_approve_applies_valid_items_and_saves_one_line(as_user, patched_db, conv, proposal):
    r = await as_user.client.post(f"/api/profile/proposals/{proposal.id}/approve")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["proposal"]["status"] == "applied"
    assert [i["result"]["status"] for i in body["proposal"]["items"]] == ["applied", "applied", "skipped"]
    line = "Done. Added 2 friends: Kazrok and Brightmane. Skipped 1: Nightpaw (already a friend)."
    assert body["follow_up"]["content"] == line
    assert body["follow_up"]["role"] == "agent"
    assert await _friends(as_user.client) == ["Brightmane", "Kazrok", "Nightpaw"]
    assert await _agent_lines(patched_db, conv, as_user.tenant_id) == [line]


async def test_second_approve_returns_the_stored_result_without_a_second_line(as_user, patched_db, conv, proposal):
    first = (await as_user.client.post(f"/api/profile/proposals/{proposal.id}/approve")).json()
    again = await as_user.client.post(f"/api/profile/proposals/{proposal.id}/approve")
    assert again.status_code == 200
    assert again.json()["proposal"] == first["proposal"]
    assert again.json()["follow_up"] is None
    assert await _friends(as_user.client) == ["Brightmane", "Kazrok", "Nightpaw"]  # written once
    assert len(await _agent_lines(patched_db, conv, as_user.tenant_id)) == 1


async def test_cancel_writes_nothing(as_user, patched_db, conv, proposal):
    r = await as_user.client.post(f"/api/profile/proposals/{proposal.id}/cancel")
    assert r.status_code == 200
    assert r.json()["proposal"]["status"] == "cancelled"
    assert r.json()["follow_up"]["content"] == "Cancelled. Your profile is unchanged."
    assert await _friends(as_user.client) == ["Nightpaw"]
    again = await as_user.client.post(f"/api/profile/proposals/{proposal.id}/cancel")
    assert again.status_code == 200 and again.json()["follow_up"] is None
    assert len(await _agent_lines(patched_db, conv, as_user.tenant_id)) == 1


@pytest.mark.parametrize("action", ["approve", "cancel"])
async def test_expired_proposal_is_refused(as_user, patched_db, conv, proposal, monkeypatch, action):
    _expire(monkeypatch)
    r = await as_user.client.post(f"/api/profile/proposals/{proposal.id}/{action}")
    assert r.status_code == 409 and r.json()["detail"] == "proposal_expired"
    assert await _friends(as_user.client) == ["Nightpaw"]
    assert await _agent_lines(patched_db, conv, as_user.tenant_id) == []


async def test_cancel_after_approve_is_refused(as_user, proposal):
    await as_user.client.post(f"/api/profile/proposals/{proposal.id}/approve")
    r = await as_user.client.post(f"/api/profile/proposals/{proposal.id}/cancel")
    assert r.status_code == 409 and r.json()["detail"] == "proposal_applied"


async def test_approve_after_cancel_is_refused(as_user, proposal):
    await as_user.client.post(f"/api/profile/proposals/{proposal.id}/cancel")
    r = await as_user.client.post(f"/api/profile/proposals/{proposal.id}/approve")
    assert r.status_code == 409 and r.json()["detail"] == "proposal_cancelled"
    assert await _friends(as_user.client) == ["Nightpaw"]


async def test_another_tenants_proposal_is_not_found(as_user, make_authed_client, proposal):
    other = await make_authed_client("other@example.com")
    try:
        for action in ("approve", "cancel"):
            r = await other.client.post(f"/api/profile/proposals/{proposal.id}/{action}")
            assert r.status_code == 404 and r.json()["detail"] == "not_found"
    finally:
        await other.client.aclose()
    assert await _friends(as_user.client) == ["Nightpaw"]
    unknown = await as_user.client.post(f"/api/profile/proposals/{uuid.uuid4()}/approve")
    assert unknown.status_code == 404


async def test_approve_without_csrf_is_refused(as_user, proposal):
    r = await as_user.client.post(
        f"/api/profile/proposals/{proposal.id}/approve", headers={"x-csrf-token": ""}
    )
    assert r.status_code in (401, 403)
    assert await _friends(as_user.client) == ["Nightpaw"]


async def test_approval_goes_through_the_shared_service(as_user, proposal, monkeypatch):
    calls = []
    real = proposals.execute_proposal

    async def spy(identity, proposal_id):
        calls.append(proposal_id)
        return await real(identity, proposal_id)

    monkeypatch.setattr(proposals, "execute_proposal", spy)
    r = await as_user.client.post(f"/api/profile/proposals/{proposal.id}/approve")
    assert r.status_code == 200
    assert calls == [proposal.id]


# --- The follow-up line (design #followup) ----------------------------------------------


def _item(index, name, action="add", target="friend", status="applied", code=None, raid_role=None):
    return {
        "index": index, "action": action, "target": target, "name": name, "realm": "Tarren Mill",
        "region": "eu", "raid_role": raid_role, "validation": {"ok": status != "skipped", "code": code},
        "result": {"status": status, "code": code},
    }


def _applied(*items):
    now = datetime.now(UTC)
    return ProfileProposalOut(
        id=uuid.uuid4(), conversation_id=uuid.uuid4(), status="applied", created_at=now,
        expires_at=now, applied_at=now, items=list(items),
    )


def test_follow_up_names_removals_and_role_changes():
    text = routes.follow_up_text(
        _applied(_item(0, "Nightpaw", action="remove"), _item(1, "Velyra", action="update", raid_role="healer"))
    )
    assert text == "Done. Removed 1 friend: Nightpaw. Set Velyra's role to healer."


def test_follow_up_reports_a_failed_item():
    text = routes.follow_up_text(
        _applied(
            _item(0, "Kazrok"),
            _item(1, "Brightmane"),
            _item(2, "Velyra", status="failed", code="duplicate_friend"),
        )
    )
    assert text == "Added 2 friends: Kazrok and Brightmane. Couldn't add Velyra (already a friend). Nothing else changed."


def test_follow_up_when_nothing_applied_and_own_characters():
    assert routes.follow_up_text(_applied(_item(0, "Ziri", status="skipped", code="invalid_realm"))) == (
        "Nothing was applied. Skipped 1: Ziri (realm unknown, add by hand)."
    )
    assert routes.follow_up_text(_applied(_item(0, "Ziri", target="own"), _item(1, "Ora", target="own"), _item(2, "Pell", target="own"))) == (
        "Done. Added 3 own characters: Ziri, Ora and Pell."
    )
