"""The agent's profile tool (feature 029 / sc-205): proposes, never writes, fails closed.

Design C5–C7, C14. No model or WCL calls: the tool is called directly with a stand-in
``ToolContext``, and one offline turn runs through the real ADK Runner with a scripted model.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from google.adk.tools.function_tool import FunctionTool

from backend.app.agent_tools.profile_tools import PROFILE_TOOLS, propose_profile_changes
from backend.app.db import repository as repo
from backend.app.db.models import ProfileProposal, UserCharacter
from backend.app.schemas import ProfileChangeIn, ProfileProposalOut
from backend.app.tenancy.context import RequestIdentity, current_identity


def _identity(tenant_id: uuid.UUID) -> RequestIdentity:
    return RequestIdentity(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        membership_role="tenant_admin",
        is_platform_admin=False,
        session_id=uuid.uuid4(),
    )


def _ctx(user_id: str, session_id: str) -> SimpleNamespace:
    """The two ToolContext attributes the tool reads (ADK user_id and the session)."""
    return SimpleNamespace(user_id=user_id, session=SimpleNamespace(id=session_id))


def _change(name="Thrall", **kw) -> ProfileChangeIn:
    return ProfileChangeIn(**{"action": "add", "target": "friend", "name": name, "realm": "Tarren Mill", "region": "eu", **kw})


@pytest.fixture
async def conv(patched_db, tenant_id) -> uuid.UUID:
    async with patched_db() as db:
        conversation = await repo.create_conversation(db, "gemini-3.6-flash", tenant_id=tenant_id)
        await db.commit()
        return conversation.id


@pytest.fixture
def me(tenant_id):
    identity = _identity(tenant_id)
    token = current_identity.set(identity)
    yield identity
    current_identity.reset(token)


async def _counts(patched_db) -> tuple[int, int]:
    async with patched_db() as db:
        chars = await db.scalar(sa.select(sa.func.count()).select_from(UserCharacter))
        props = await db.scalar(sa.select(sa.func.count()).select_from(ProfileProposal))
        return chars, props


# --- The tool ------------------------------------------------------------------------


async def test_returns_the_contract_shape_and_never_writes(me, conv, patched_db, tenant_id):
    result = await propose_profile_changes(
        [_change("Jaina"), _change("Bad Name"), _change("Thrall", raid_role="healer")],
        _ctx(str(tenant_id), str(conv)),
    )
    assert result["status"] == "success"
    assert result["note"] == "Nothing has changed yet. The user approves or cancels on the card."
    proposal = ProfileProposalOut.model_validate(result["proposal"])  # the contract shape
    assert proposal.status == "pending" and proposal.conversation_id == conv
    assert [i.validation.code for i in proposal.items] == [None, "invalid_name", None]
    assert "tenant_id" not in result["proposal"] and "user_id" not in result["proposal"]
    assert await _counts(patched_db) == (0, 1)  # one proposal row, no profile write
    async with patched_db() as db:
        row = await db.get(ProfileProposal, proposal.id)
        assert (row.tenant_id, row.user_id, row.conversation_id) == (tenant_id, me.user_id, conv)


async def test_too_many_or_no_changes_is_a_tool_error(me, conv, patched_db, tenant_id):
    ctx = _ctx(str(tenant_id), str(conv))
    many = [_change(f"Pal{chr(97 + i % 26)}{chr(97 + i // 26)}") for i in range(31)]
    too_many = await propose_profile_changes(many, ctx)
    assert too_many["status"] == "error" and "at most 30" in too_many["error_message"]
    assert (await propose_profile_changes([], ctx))["status"] == "error"
    assert await _counts(patched_db) == (0, 0)


async def test_fails_closed_without_an_identity(conv, patched_db, tenant_id):
    # The greeting and the guide / guild-summary jobs share this runner: no identity there.
    assert current_identity.get() is None
    for session_id in (str(conv), "greeting-gemini-3.6-flash-abc", f"guide-{uuid.uuid4().hex}"):
        for user_id in (str(tenant_id), "local_user"):
            result = await propose_profile_changes([_change()], _ctx(user_id, session_id))
            assert result == {"status": "error", "error_message": "Profile changes are unavailable in this session."}
    assert await _counts(patched_db) == (0, 0)


async def test_fails_closed_on_a_mismatch(me, conv, patched_db, tenant_id, other_tenant_id):
    async with patched_db() as db:
        foreign = await repo.create_conversation(db, "m", tenant_id=other_tenant_id)
        await db.commit()
    cases = [
        _ctx(str(other_tenant_id), str(conv)),  # ADK session of another tenant
        _ctx("local_user", str(conv)),  # the shared runner's default user (greeting, guides)
        _ctx(str(tenant_id), f"guide-{uuid.uuid4().hex}"),  # not a chat session
        _ctx(str(tenant_id), str(foreign.id)),  # another tenant's conversation
    ]
    for ctx in cases:
        result = await propose_profile_changes([_change()], ctx)
        assert result["status"] == "error", ctx
    assert await _counts(patched_db) == (0, 0)


# --- Declaration and registration -------------------------------------------------------


def test_declaration_has_no_identity_parameters_for_gemini_and_claude():
    from google.adk.models.anthropic_llm import function_declaration_to_tool_param

    declaration = FunctionTool(propose_profile_changes)._get_declaration()
    schema = declaration.parameters_json_schema
    assert list(schema["properties"]) == ["changes"]  # no tenant, user, conversation or id
    item = schema["$defs"]["ProfileChangeIn"]["properties"]
    assert {"action", "target", "name", "realm", "region", "raid_role", "played_role"} <= set(item)
    assert not {"tenant_id", "user_id", "conversation_id", "character_id", "id"} & set(item)
    claude = function_declaration_to_tool_param(declaration)
    assert claude["name"] == "propose_profile_changes"
    assert list(claude["input_schema"]["properties"]) == ["changes"]


def test_profile_group_is_noted_and_its_summary_line_fits():
    from wcl_agent.capabilities import MAX_TOOL_LINE_CHARS, render_capability_summary

    assert PROFILE_TOOLS.note and PROFILE_TOOLS.tools == (propose_profile_changes,)
    summary = render_capability_summary([PROFILE_TOOLS], web_search=True)
    line = next(l for l in summary.splitlines() if l.startswith("- propose_profile_changes:"))
    assert len(line) <= MAX_TOOL_LINE_CHARS and line.endswith("until the user approves.")
    assert "when the user asks" in summary  # no unsolicited proposals from guide/summary prompts
