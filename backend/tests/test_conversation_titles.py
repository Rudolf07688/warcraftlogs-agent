"""Generated conversation titles (feature 019 / sc-155).

Covers the title-source rules: chats named at creation are marked explicit by every
naming caller (FR-018), the one-time generation claim (FR-016), title cleaning (FR-013),
the background job and its failure fallback (FR-015/017), and the chat-turn hook and
its frame (FR-019). The model is always faked.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from backend.app.api import ws as ws_mod
from backend.app.db import repository as repo
from backend.app.schemas import ChatTurn
from backend.app.services import background, conversation_titles
from backend.app.services.conversation_titles import TITLE_MAX_LEN, clean_title
from backend.app.tenancy.context import RequestIdentity
from wcl_agent.llm.model_retry import ModelRateLimited

# conftest stubs scheduling for every other test; the hook tests here put it back.
_real_schedule_title = conversation_titles.schedule_title

_MODEL = "gemini-3.6-flash"
_OLD = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _title_source(session_factory, conv_id, tenant_id) -> str:
    async with session_factory() as s:
        conv = await repo.get_conversation_row(s, uuid.UUID(str(conv_id)), tenant_id=tenant_id)
        return conv.title_source


# --- Explicit at creation, per naming caller (FR-018) ----------------------------


async def test_post_with_title_is_explicit_and_without_is_auto(as_user, session_factory):
    model = (await as_user.client.get("/api/models")).json()["default"]
    named = await as_user.client.post("/api/conversations", json={"model": model, "title": "Prog notes"})
    unnamed = await as_user.client.post("/api/conversations", json={"model": model})
    assert named.status_code == unnamed.status_code == 201

    assert await _title_source(session_factory, named.json()["id"], as_user.tenant_id) == "explicit"
    assert await _title_source(session_factory, unnamed.json()["id"], as_user.tenant_id) == "auto"


async def test_tracked_raid_investigation_is_explicit(as_user, session_factory):
    async with session_factory() as s:
        await repo.upsert_tracked_raid(
            s, tenant_id=as_user.tenant_id, report_code="RRRR", label="R raid"
        )
        await s.commit()

    resp = await as_user.client.post("/api/raids/RRRR/investigate", json={})
    assert resp.status_code == 201, resp.text
    conv_id = resp.json()["conversation_id"]
    assert await _title_source(session_factory, conv_id, as_user.tenant_id) == "explicit"


async def test_recent_raid_kickoff_is_explicit(as_user, session_factory):
    from backend.app.services.recent_raid_types import ListedReport

    started = datetime(2026, 10, 15, 19, 0, tzinfo=timezone.utc)
    async with session_factory() as s:
        char = await repo.add_character(
            s, tenant_id=as_user.tenant_id, role="self", name="Alpha", server="Realm", region="EU"
        )
        await repo.upsert_listed_reports(
            s,
            tenant_id=as_user.tenant_id,
            reports=[
                ListedReport(
                    code="RECENT1",
                    title="Title",
                    zone_id=53,
                    zone_name="The Venomous Abyss",
                    guild_name="Guild",
                    started_at=started,
                    ended_at=started,
                    character_ids=frozenset({char.id}),
                    is_raid=True,
                )
            ],
        )
        await s.commit()

    # The welcome page's recent-raid card starts its chat through the same endpoint.
    resp = await as_user.client.post("/api/raids/RECENT1/investigate", json={})
    assert resp.status_code == 201, resp.text
    conv_id = resp.json()["conversation_id"]
    assert await _title_source(session_factory, conv_id, as_user.tenant_id) == "explicit"


async def test_chat_started_over_the_socket_is_auto(session, tenant_id):
    # The WebSocket path creates the conversation without a title.
    conv = await repo.create_conversation(session, model=_MODEL, tenant_id=tenant_id)
    assert conv.title_source == "auto" and conv.title == "New chat"


# --- The one-time claim (FR-016) -------------------------------------------------


async def _conversation(session, tenant_id, *, title=None, source=None):
    conv = await repo.create_conversation(session, model=_MODEL, title=title, tenant_id=tenant_id)
    if source:
        conv.title_source = source
    conv.updated_at = _OLD
    await session.commit()
    return conv


async def test_claim_succeeds_once(session, tenant_id):
    conv = await _conversation(session, tenant_id)
    assert await repo.claim_title_generation(session, conv.id, tenant_id=tenant_id) is True
    assert await repo.claim_title_generation(session, conv.id, tenant_id=tenant_id) is False


@pytest.mark.parametrize("source", ["explicit", "legacy"])
async def test_named_and_legacy_chats_are_never_claimed(session, tenant_id, source):
    conv = await _conversation(session, tenant_id, title="Named", source=source)
    assert await repo.claim_title_generation(session, conv.id, tenant_id=tenant_id) is False


async def test_claim_is_tenant_scoped(session, tenant_id, other_tenant_id):
    conv = await _conversation(session, tenant_id)
    assert await repo.claim_title_generation(session, conv.id, tenant_id=other_tenant_id) is False
    assert await repo.claim_title_generation(session, conv.id, tenant_id=tenant_id) is True


async def test_generated_title_needs_a_claim_and_keeps_updated_at(session, tenant_id):
    conv = await _conversation(session, tenant_id)
    assert await repo.set_generated_title(session, conv.id, "Too early", tenant_id=tenant_id) is False

    await repo.claim_title_generation(session, conv.id, tenant_id=tenant_id)
    assert await repo.set_generated_title(session, conv.id, "Wipe review", tenant_id=tenant_id) is True
    await session.refresh(conv)
    assert conv.title == "Wipe review" and conv.title_source == "generated"
    assert conv.updated_at.replace(tzinfo=timezone.utc) == _OLD


async def test_generated_title_never_overwrites_an_explicit_name(session, tenant_id):
    conv = await _conversation(session, tenant_id, title="Raid: Undermine")
    assert await repo.set_generated_title(session, conv.id, "Other", tenant_id=tenant_id) is False


async def test_generated_title_on_a_deleted_chat_is_a_no_op(session, tenant_id):
    conv = await _conversation(session, tenant_id)
    await repo.claim_title_generation(session, conv.id, tenant_id=tenant_id)
    await repo.delete_conversation(session, conv.id, tenant_id=tenant_id)
    assert await repo.set_generated_title(session, conv.id, "Gone", tenant_id=tenant_id) is False


# --- Title cleaning (FR-013) -------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"Wipes on Gallywix"', "Wipes on Gallywix"),
        ("“Curly quotes”", "Curly quotes"),
        ("`Parse` review", "Parse review"),
        ("**Title:** Raid recap", "Raid recap"),
        ("Title: Healer cooldowns.", "Healer cooldowns"),
        ("# Heading\nsecond line", "Heading"),
        ("\n\n  Mythic   prog \t notes  ", "Mythic prog notes"),
        ("...", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_clean_title(raw, expected):
    assert clean_title(raw) == expected


def test_clean_title_cuts_at_a_word_boundary():
    title = clean_title("Why our raid kept wiping on the last boss " * 3)
    assert len(title) <= TITLE_MAX_LEN
    assert not title.endswith(" ")
    assert ("Why our raid kept wiping on the last boss " * 3).startswith(title + " ")


def test_clean_title_hard_cuts_a_single_long_word():
    assert clean_title("x" * 80) == "x" * TITLE_MAX_LEN


# --- The background job (FR-015, FR-017) -------------------------------------------


def _identity(tenant_id) -> RequestIdentity:
    return RequestIdentity(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        membership_role="tenant_admin",
        is_platform_admin=False,
        session_id=uuid.uuid4(),
    )


async def _seed(session_factory, tenant_id, *, title=None, first_message="how did last night go"):
    async with session_factory() as s:
        conv = await repo.create_conversation(s, model=_MODEL, title=title, tenant_id=tenant_id)
        await repo.add_message(s, conv.id, "user", first_message, tenant_id=tenant_id)
        await s.commit()
        return conv.id


async def _row(session_factory, conv_id, tenant_id):
    async with session_factory() as s:
        return await repo.get_conversation_row(s, conv_id, tenant_id=tenant_id)


class _Notify:
    def __init__(self, fail: bool = False) -> None:
        self.titles: list[str] = []
        self.fail = fail

    async def __call__(self, title: str) -> None:
        self.titles.append(title)
        if self.fail:
            raise RuntimeError("socket closed")


def _fake_generate(monkeypatch, result):
    calls = []

    async def generate(question, answer):
        calls.append((question, answer))
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(conversation_titles, "generate_title", generate)
    return calls


async def test_job_saves_the_title_and_notifies_once(patched_db, tenant_id, monkeypatch):
    conv_id = await _seed(patched_db, tenant_id)
    calls = _fake_generate(monkeypatch, "Last night's raid review")
    notify = _Notify()

    await conversation_titles.retitle_conversation(
        conv_id, _identity(tenant_id), "how did last night go", "You wiped 12 times.", notify
    )

    row = await _row(patched_db, conv_id, tenant_id)
    assert row.title == "Last night's raid review" and row.title_source == "generated"
    assert notify.titles == ["Last night's raid review"]
    assert calls == [("how did last night go", "You wiped 12 times.")]


async def test_job_runs_at_most_once(patched_db, tenant_id, monkeypatch):
    conv_id = await _seed(patched_db, tenant_id)
    calls = _fake_generate(monkeypatch, "First title")
    identity = _identity(tenant_id)
    await conversation_titles.retitle_conversation(conv_id, identity, "q", "a", _Notify())
    notify = _Notify()
    await conversation_titles.retitle_conversation(conv_id, identity, "q2", "a2", notify)

    assert len(calls) == 1 and notify.titles == []
    assert (await _row(patched_db, conv_id, tenant_id)).title == "First title"


async def test_concurrent_jobs_call_the_model_once(patched_db, tenant_id, monkeypatch):
    conv_id = await _seed(patched_db, tenant_id)
    calls = _fake_generate(monkeypatch, "Only once")
    identity = _identity(tenant_id)
    await asyncio.gather(
        *(conversation_titles.retitle_conversation(conv_id, identity, "q", "a", _Notify()) for _ in range(3))
    )
    assert len(calls) == 1


async def test_explicit_title_is_never_claimed(patched_db, tenant_id, monkeypatch):
    conv_id = await _seed(patched_db, tenant_id, title="Raid: Liberation of Undermine")
    calls = _fake_generate(monkeypatch, "Other")
    notify = _Notify()
    await conversation_titles.retitle_conversation(conv_id, _identity(tenant_id), "q", "a", notify)

    row = await _row(patched_db, conv_id, tenant_id)
    assert row.title == "Raid: Liberation of Undermine" and row.title_source == "explicit"
    assert calls == [] and notify.titles == []


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("model down"), ModelRateLimited(2, 4.0, RuntimeError("429")), TimeoutError()],
)
async def test_failure_keeps_the_excerpt_and_is_not_retried(patched_db, tenant_id, monkeypatch, failure):
    conv_id = await _seed(patched_db, tenant_id, first_message="hey can you look at our raid")
    _fake_generate(monkeypatch, failure)
    notify = _Notify()

    await conversation_titles.retitle_conversation(conv_id, _identity(tenant_id), "q", "a", notify)

    row = await _row(patched_db, conv_id, tenant_id)
    assert row.title == "hey can you look at our raid"  # the first-message excerpt stays
    assert row.title_source == "generated"  # claimed: never attempted again
    assert notify.titles == []


async def test_hung_model_is_cut_off_by_the_timeout(patched_db, tenant_id, monkeypatch):
    conv_id = await _seed(patched_db, tenant_id, first_message="excerpt")

    async def hang(question, answer):
        await asyncio.sleep(60)

    monkeypatch.setattr(conversation_titles, "generate_title", hang)
    monkeypatch.setattr(conversation_titles, "TITLE_TIMEOUT_S", 0.05)
    await conversation_titles.retitle_conversation(conv_id, _identity(tenant_id), "q", "a", _Notify())
    assert (await _row(patched_db, conv_id, tenant_id)).title == "excerpt"


async def test_empty_title_keeps_the_excerpt(patched_db, tenant_id, monkeypatch):
    conv_id = await _seed(patched_db, tenant_id, first_message="excerpt")
    _fake_generate(monkeypatch, "")
    notify = _Notify()
    await conversation_titles.retitle_conversation(conv_id, _identity(tenant_id), "q", "a", notify)
    assert (await _row(patched_db, conv_id, tenant_id)).title == "excerpt"
    assert notify.titles == []


async def test_chat_deleted_meanwhile_is_a_quiet_no_op(patched_db, tenant_id, monkeypatch):
    conv_id = await _seed(patched_db, tenant_id)

    async def generate_then_delete(question, answer):
        async with patched_db() as s:
            await repo.delete_conversation(s, conv_id, tenant_id=tenant_id)
            await s.commit()
        return "Too late"

    monkeypatch.setattr(conversation_titles, "generate_title", generate_then_delete)
    notify = _Notify()
    await conversation_titles.retitle_conversation(conv_id, _identity(tenant_id), "q", "a", notify)
    assert notify.titles == []
    assert await _row(patched_db, conv_id, tenant_id) is None


async def test_closed_socket_is_swallowed_and_the_title_kept(patched_db, tenant_id, monkeypatch):
    conv_id = await _seed(patched_db, tenant_id)
    _fake_generate(monkeypatch, "Saved anyway")
    await conversation_titles.retitle_conversation(
        conv_id, _identity(tenant_id), "q", "a", _Notify(fail=True)
    )
    assert (await _row(patched_db, conv_id, tenant_id)).title == "Saved anyway"


# --- The model call (FR-014) ---------------------------------------------------------


def _fake_client(monkeypatch, responses):
    """A genai client whose ``generate_content`` returns or raises each item in turn."""
    seen = []

    class _Models:
        async def generate_content(self, *, model, contents, config):
            seen.append(SimpleNamespace(model=model, contents=contents, config=config))
            item = responses[len(seen) - 1]
            if isinstance(item, BaseException):
                raise item
            return SimpleNamespace(text=item)

    monkeypatch.setattr(
        conversation_titles.suggestions, "_get_client", lambda: SimpleNamespace(aio=SimpleNamespace(models=_Models()))
    )
    return seen


def _rate_limited() -> genai_errors.APIError:
    return genai_errors.APIError(429, {"error": {"code": 429, "message": "busy", "status": "RESOURCE_EXHAUSTED"}})


async def _no_sleep(_delay):
    return None


async def test_generate_title_uses_the_cheap_model_and_cleans_the_reply(monkeypatch):
    seen = _fake_client(monkeypatch, ['"**Wipes on the last boss.**"'])
    title = await conversation_titles.generate_title("why do we wipe", "Because of the soak.")
    assert title == "Wipes on the last boss"
    [call] = seen
    assert call.model == conversation_titles.suggestions._SUGGEST_MODEL
    assert call.config.thinking_config.thinking_budget == 0
    assert "why do we wipe" in call.contents and "Because of the soak." in call.contents


async def test_generate_title_retries_one_rate_limit(monkeypatch):
    monkeypatch.setattr("wcl_agent.llm.model_retry.asyncio.sleep", _no_sleep)
    seen = _fake_client(monkeypatch, [_rate_limited(), "Healer cooldown plan"])
    assert await conversation_titles.generate_title("q", "a") == "Healer cooldown plan"
    assert len(seen) == 2


async def test_generate_title_gives_up_after_the_second_rate_limit(monkeypatch):
    monkeypatch.setattr("wcl_agent.llm.model_retry.asyncio.sleep", _no_sleep)
    _fake_client(monkeypatch, [_rate_limited(), _rate_limited(), "never reached"])
    with pytest.raises(ModelRateLimited):
        await conversation_titles.generate_title("q", "a")


# --- The chat-turn hook and its frame (FR-015, FR-019) --------------------------------


class _FakeSocket:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.frames.append(payload)


@pytest.fixture
def turn_env(monkeypatch):
    """Fake model stream and suggestions; the real scheduler; a recording title model."""

    async def stream(*args, **kwargs):
        yield {"type": "token", "text": "You wiped on the soak."}

    async def suggest(*args, **kwargs):
        return []

    monkeypatch.setattr(ws_mod, "stream_response", stream)
    monkeypatch.setattr(ws_mod, "generate_followups", suggest)
    monkeypatch.setattr(ws_mod, "set_refresh_actor", lambda *_: None)
    monkeypatch.setattr(conversation_titles, "schedule_title", _real_schedule_title)
    return _fake_generate(monkeypatch, "Soak wipes review")


async def _turn(sock, identity, content, conversation_id=None):
    turn = ChatTurn(model=_MODEL, content=content, conversation_id=conversation_id)
    task = await ws_mod._handle_turn(sock, turn, identity)
    await task  # follow-up suggestions
    await asyncio.gather(*list(background._bg_tasks))  # the title job, if any


async def test_first_reply_gets_a_title_frame_after_done(as_user, patched_db, turn_env):
    sock = _FakeSocket()
    identity = _identity(as_user.tenant_id)
    await _turn(sock, identity, "why do we keep wiping")

    types = [f["type"] for f in sock.frames]
    assert types.index("done") < types.index("conversation_title")
    conv_id = sock.frames[0]["conversation_id"]
    frame = sock.frames[types.index("conversation_title")]
    assert frame == {"type": "conversation_title", "conversation_id": conv_id, "title": "Soak wipes review"}
    assert turn_env == [("why do we keep wiping", "You wiped on the soak.")]

    # Later turns in the same chat schedule nothing.
    sock2 = _FakeSocket()
    await _turn(sock2, identity, "and the healers?", conversation_id=uuid.UUID(conv_id))
    assert "conversation_title" not in [f["type"] for f in sock2.frames]
    assert len(turn_env) == 1


async def test_raid_investigation_chat_gets_no_title_job(as_user, patched_db, turn_env):
    async with patched_db() as s:
        await repo.upsert_tracked_raid(s, tenant_id=as_user.tenant_id, report_code="RRRR", label="R raid")
        await s.commit()
    resp = await as_user.client.post("/api/raids/RRRR/investigate", json={})
    conv_id = uuid.UUID(resp.json()["conversation_id"])

    sock = _FakeSocket()
    await _turn(sock, _identity(as_user.tenant_id), "investigate RRRR", conversation_id=conv_id)
    assert "conversation_title" not in [f["type"] for f in sock.frames]
    assert turn_env == []
