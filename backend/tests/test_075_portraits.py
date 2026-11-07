"""Character portraits from the Blizzard Profile API (feature 075, sc-363).

Blizzard is a fake ``httpx.MockTransport`` that records every request it receives, so each
hostile-input guard is asserted where it takes effect: the URL that would have left the
process, or the ``portrait_url`` the endpoint hands to ``<img src>``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import unquote

import httpx
import pytest
from pydantic import SecretStr

from backend.app.config import settings
from backend.app.db import repository as repo
from backend.app.services import portraits
from backend.app.services.portraits import CharacterRef
from wcl_agent.cache.cache import keys

SECRET = "blz-client-secret-xyz"
TOKEN = "blz-access-token-abc"
AVATAR = "https://render.worldofwarcraft.com/eu/character/twilights-hammer/23/108025623-avatar.jpg"


class FakeBlizzard:
    """Answers the token and character-media endpoints; ``media`` maps a lower-case name to
    an ``httpx.Response`` (or a callable/exception). Unknown names get 404."""

    def __init__(self, media: dict | None = None, token_status: int = 200):
        self.media = media or {}
        self.token_status = token_status
        self.requests: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "oauth.battle.net":
            if self.token_status != 200:
                return httpx.Response(self.token_status, text="no")
            return httpx.Response(200, json={"access_token": TOKEN, "token_type": "bearer", "expires_in": 86399})
        name = unquote(request.url.raw_path.decode().split("?")[0].split("/")[-2])
        answer = self.media.get(name, httpx.Response(404, json={"code": 404}))
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            return await answer(request)
        return answer

    @property
    def media_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host != "oauth.battle.net"]


def media_json(avatar: object = AVATAR) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "_links": {},
            "character": {},
            "assets": [
                {"key": "main-raw", "value": "https://render.worldofwarcraft.com/eu/x-main-raw.png"},
                {"key": "avatar", "value": avatar},
            ],
        },
    )


@pytest.fixture
def blizzard(monkeypatch):
    fake = FakeBlizzard()
    monkeypatch.setattr(settings, "blizzard_client_id", "blz-client-id")
    monkeypatch.setattr(settings, "blizzard_client_secret", SecretStr(SECRET))
    monkeypatch.setattr(
        portraits,
        "_http_client",
        lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(fake), timeout=portraits.HTTP_TIMEOUT_S, follow_redirects=False
        ),
    )
    portraits._tokens.clear()
    portraits._token_backoff.clear()
    yield fake
    portraits._tokens.clear()
    portraits._token_backoff.clear()


async def _seed(session_factory, tenant_id, *chars: tuple[str, str, str, str]) -> None:
    async with session_factory() as s:
        for role, name, server, region in chars:
            await repo.add_character(s, tenant_id=tenant_id, role=role, name=name, server=server, region=region)
        await s.commit()


async def _portraits(client) -> dict[str, str | None]:
    resp = await client.get("/api/profile/portraits")
    assert resp.status_code == 200
    return {p["name"]: p["portrait_url"] for p in resp.json()["portraits"]}


# --- the endpoint (FR-002, contract) ---------------------------------------------------------


async def test_endpoint_serves_own_and_friend_portraits(as_user, session_factory, blizzard):
    blizzard.media["traecie"] = media_json()
    await _seed(
        session_factory,
        as_user.tenant_id,
        ("self", "Traecie", "Twilight's Hammer", "EU"),
        ("friend", "Nobody", "Twilight's Hammer", "EU"),
    )
    resp = await as_user.client.get("/api/profile/portraits")
    assert resp.status_code == 200
    body = resp.json()["portraits"]
    assert [(p["name"], p["server"], p["region"], p["portrait_url"]) for p in body] == [
        ("Traecie", "Twilight's Hammer", "eu", AVATAR),
        ("Nobody", "Twilight's Hammer", "eu", None),  # 404: initials
    ]
    assert all(p["character_id"] for p in body)
    sent = blizzard.media_requests[0]
    assert str(sent.url).startswith(
        "https://eu.api.blizzard.com/profile/wow/character/twilights-hammer/traecie/character-media?"
    )
    assert sent.url.params["namespace"] == "profile-eu"
    assert sent.headers["authorization"] == f"Bearer {TOKEN}"


async def test_endpoint_needs_a_session(client):
    assert (await client.get("/api/profile/portraits")).status_code == 401


async def test_endpoint_covers_only_the_callers_profile(as_user, make_authed_client, session_factory, blizzard):
    """Workspace B's endpoint returns B's characters only, never A's, whatever the query says
    and whatever A's lookups put in the shared cache."""
    blizzard.media["alpha"] = media_json()
    tenant_b = await make_authed_client("userb@example.com")
    try:
        await _seed(session_factory, as_user.tenant_id, ("self", "Alpha", "Draenor", "EU"))
        await _seed(session_factory, tenant_b.tenant_id, ("self", "Bravo", "Draenor", "EU"))
        assert await _portraits(as_user.client) == {"Alpha": AVATAR}
        resp = await tenant_b.client.get("/api/profile/portraits", params={"name": "Alpha", "server": "Draenor"})
        assert [p["name"] for p in resp.json()["portraits"]] == ["Bravo"]
    finally:
        await tenant_b.client.aclose()


# --- the cache (FR-003, FR-007) ---------------------------------------------------------------


async def test_found_portrait_is_cached_for_a_day(as_user, session_factory, blizzard, fake_redis):
    blizzard.media["traecie"] = media_json()
    await _seed(session_factory, as_user.tenant_id, ("self", "Traecie", "Twilight's Hammer", "EU"))
    assert await _portraits(as_user.client) == {"Traecie": AVATAR}
    assert await _portraits(as_user.client) == {"Traecie": AVATAR}
    assert len(blizzard.media_requests) == 1  # the second page load asked nobody
    key = keys.char_portrait("eu", "twilights-hammer", "traecie")
    assert 86400 <= await fake_redis.ttl(key) <= 86400 * 1.1 + 1


@pytest.mark.parametrize(
    ("answer", "max_ttl"),
    [
        (httpx.Response(404), portraits.NONE_TTL_S),
        (httpx.Response(503), portraits.UNAVAILABLE_TTL_S),
        (httpx.Response(429), portraits.UNAVAILABLE_TTL_S),
        (httpx.ConnectError("down"), portraits.UNAVAILABLE_TTL_S),
    ],
)
async def test_failures_are_negatively_cached_for_less(blizzard, fake_redis, answer, max_ttl):
    """Blizzard down or rate limiting: one call, then a short "unavailable" entry, not a call per
    page load. Not found: a longer "none" entry."""
    blizzard.media["traecie"] = answer
    char = CharacterRef("eu", "Twilight's Hammer", "Traecie")
    assert await portraits.portrait_url(char) is None
    assert await portraits.portrait_url(char) is None
    assert len(blizzard.media_requests) == 1
    ttl = await fake_redis.ttl(keys.char_portrait("eu", "twilights-hammer", "traecie"))
    assert 0 < ttl <= max_ttl * 1.1 + 1
    assert max_ttl == portraits.UNAVAILABLE_TTL_S or ttl > portraits.UNAVAILABLE_TTL_S * 1.1


@pytest.mark.parametrize(
    ("region", "realm", "name"),
    [("eu", "a:b", "x"), ("eu", "*", "x"), ("eu", "Draenor", "x" * 24), ("eu", "a-b", "c"), ("eu", "a", "b-c")],
)
def test_cache_key_is_hashed_and_bounded(region, realm, name):
    key = keys.char_portrait(region, realm, name)
    assert re.fullmatch(r"ext:portrait:v1:[0-9a-f]{32}", key)


def test_cache_key_is_injective_across_field_boundaries():
    assert keys.char_portrait("eu", "a-b", "c") != keys.char_portrait("eu", "a", "b-c")
    assert keys.char_portrait("eu", "ab", "c") != keys.char_portrait("eu", "a", "bc")


# --- outbound URL guards (FR-005) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("realm", "name"),
    [
        ("Draenor", "a/b"),
        ("Draenor", "a\\b"),
        ("Draenor", ".."),
        ("..", "Traecie"),
        ("Draenor/../../oauth", "Traecie"),
        ("Draenor", "a?b"),
        ("Draenor", "a#b"),
        ("Draenor", "a%2Fb"),
        ("Draenor%2F..", "Traecie"),
        ("Draenor", "a\nb"),
        ("Draenor\n", "Tra\necie"),
        ("Draenor", "Ëlfína"),
        ("Aggra (Português)", "Traecie"),
        ("Kel'Thuzad", "Ünïcødé"),
    ],
)
async def test_outbound_url_keeps_host_and_path_prefix(blizzard, realm, name):
    await portraits.portrait_url(CharacterRef("eu", realm, name))
    for sent in blizzard.media_requests:
        assert sent.url.scheme == "https" and sent.url.host == "eu.api.blizzard.com"
        segments = sent.url.raw_path.decode().split("?")[0].split("/")
        # "", profile, wow, character, <realm>, <name>, character-media: nothing more, nothing less
        assert segments[:4] == ["", "profile", "wow", "character"] and segments[6] == "character-media"
        assert len(segments) == 7
        realm_seg, name_seg = unquote(segments[4]), unquote(segments[5])
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", realm_seg)
        assert name_seg.isalpha() and name_seg == name.strip().lower()


async def test_unicode_name_is_percent_encoded(blizzard):
    blizzard.media["ëlfína"] = media_json()
    assert await portraits.portrait_url(CharacterRef("eu", "Aggra (Português)", "Ëlfína")) == AVATAR
    sent = blizzard.media_requests[0]
    assert sent.url.raw_path.startswith(
        b"/profile/wow/character/aggra-portugues/%C3%ABlf%C3%ADna/character-media"
    )


@pytest.mark.parametrize("region", ["cn", "eu.evil.example", "evil.example/eu", "", "e u", "EUR"])
async def test_region_outside_the_allow_list_makes_no_request(blizzard, region):
    assert await portraits.portrait_url(CharacterRef(region, "Draenor", "Traecie")) is None
    assert blizzard.requests == []


async def test_region_is_case_insensitive(blizzard):
    blizzard.media["traecie"] = media_json()
    assert await portraits.portrait_url(CharacterRef(" US ", "Area 52", "Traecie")) == AVATAR
    assert blizzard.media_requests[0].url.host == "us.api.blizzard.com"


async def test_not_configured_makes_no_request(blizzard, monkeypatch):
    monkeypatch.setattr(settings, "blizzard_client_id", "")
    assert await portraits.portrait_url(CharacterRef("eu", "Draenor", "Traecie")) is None
    assert blizzard.requests == []


# --- served image URL guard (FR-004): asserted on what the endpoint returns -------------------


@pytest.mark.parametrize(
    "avatar",
    [
        "javascript:alert(1)",
        "data:image/png;base64,AAAA",
        "http://render.worldofwarcraft.com/eu/x-avatar.jpg",
        "https://evil.example/x-avatar.jpg",
        "https://render.worldofwarcraft.com.evil.example/x.jpg",
        "https://render.worldofwarcraft.com\\@evil.example/x.jpg",
        "https://render.worldofwarcraft.com@evil.example/x.jpg",
        "https://user@render.worldofwarcraft.com/x.jpg",
        "https://render.worldofwarcraft.com:8443/x.jpg",
        "//render.worldofwarcraft.com/x.jpg",
        "https://render.worldofwarcraft.com/x.jpg\n",
        "https://RENDER.worldofwarcraft.com/x.jpg",
        12345,
        None,
        "https://render.worldofwarcraft.com/" + "a" * 600,
    ],
)
async def test_only_https_render_host_urls_are_served(as_user, session_factory, blizzard, avatar):
    blizzard.media["traecie"] = media_json(avatar)
    await _seed(session_factory, as_user.tenant_id, ("self", "Traecie", "Draenor", "EU"))
    assert await _portraits(as_user.client) == {"Traecie": None}


async def test_a_bad_url_already_in_the_cache_is_not_served(blizzard, fake_redis):
    """Checked again on the way out: a cached value written by an older build or by hand."""
    key = keys.char_portrait("eu", "draenor", "traecie")
    await fake_redis.set(key, b'{"status":"found","url":"javascript:alert(1)"}', ex=60)
    assert await portraits.portrait_url(CharacterRef("eu", "Draenor", "Traecie")) is None
    assert blizzard.requests == []


# --- redirects, big bodies, timeouts ----------------------------------------------------------


async def test_redirect_is_not_followed(blizzard):
    blizzard.media["traecie"] = httpx.Response(302, headers={"location": "https://evil.example/steal"})
    assert await portraits.portrait_url(CharacterRef("eu", "Draenor", "Traecie")) is None
    assert {r.url.host for r in blizzard.requests} == {"oauth.battle.net", "eu.api.blizzard.com"}


async def test_huge_body_is_not_read_whole(blizzard):
    sent: list[int] = []

    async def stream():
        for _ in range(1000):  # 64 MiB if read to the end
            sent.append(1)
            yield b" " * 65536

    async def huge(request):
        return httpx.Response(200, content=stream(), headers={"content-type": "application/json"})

    blizzard.media["traecie"] = huge
    assert await portraits.portrait_url(CharacterRef("eu", "Draenor", "Traecie")) is None
    assert len(sent) <= 3  # stopped just past the 64 KiB cap


async def test_timeout_falls_back_and_the_page_still_loads(as_user, session_factory, blizzard, monkeypatch):
    monkeypatch.setattr(portraits, "BUDGET_S", 0.3)

    async def slow(request):
        await asyncio.sleep(2.0)
        return media_json()

    blizzard.media["slowpoke"] = slow
    blizzard.media["traecie"] = media_json()
    await _seed(
        session_factory,
        as_user.tenant_id,
        ("self", "Slowpoke", "Draenor", "EU"),
        ("self", "Traecie", "Draenor", "EU"),
    )
    started = time.monotonic()
    assert await _portraits(as_user.client) == {"Slowpoke": None, "Traecie": AVATAR}
    assert time.monotonic() - started < 1.3  # the budget, not the 2 s answer


async def test_read_timeout_is_unavailable(blizzard):
    blizzard.media["traecie"] = httpx.ReadTimeout("slow")
    assert await portraits.portrait_url(CharacterRef("eu", "Draenor", "Traecie")) is None


# --- secrets (FR-006) -------------------------------------------------------------------------


async def test_token_and_secret_never_leak(as_user, session_factory, blizzard, fake_redis, caplog):
    caplog.set_level(logging.DEBUG)
    blizzard.media["traecie"] = media_json()
    blizzard.media["broken"] = httpx.Response(500, text=f"echo {TOKEN} {SECRET}")
    blizzard.media["gone"] = httpx.ConnectError(f"failed with {TOKEN}")
    await _seed(
        session_factory,
        as_user.tenant_id,
        ("self", "Traecie", "Draenor", "EU"),
        ("friend", "Broken", "Draenor", "EU"),
        ("friend", "Gone", "Draenor", "EU"),
    )
    resp = await as_user.client.get("/api/profile/portraits")
    portraits._tokens.clear()
    portraits._token_backoff.clear()
    blizzard.token_status = 401
    await portraits.portrait_url(CharacterRef("us", "Area 52", "Fresh"))
    stored = [await fake_redis.get(k) async for k in fake_redis.scan_iter("*")]
    for secret in (TOKEN, SECRET):
        assert secret not in resp.text
        assert secret not in caplog.text
        assert not any(v and secret.encode() in v for v in stored)
    assert SECRET not in repr(settings)
    # The secret goes only to the token endpoint, as Basic auth; the token only to the media host.
    token_req = next(r for r in blizzard.requests if r.url.host == "oauth.battle.net")
    assert token_req.headers["authorization"].startswith("Basic ")
    assert all(SECRET not in str(r.url) and TOKEN not in str(r.url) for r in blizzard.requests)


# --- QA rework (D18 review:075) ---------------------------------------------------------------


async def test_slow_blizzard_becomes_a_cached_unavailable(as_user, session_factory, blizzard, fake_redis, monkeypatch):
    """SEC-001: one deadline over token + media, shorter than the endpoint's budget, so a slow
    answer is stored as "unavailable" (5 min) instead of being cancelled and asked again on
    every load."""
    monkeypatch.setattr(portraits, "FETCH_DEADLINE_S", 0.3)

    async def slow(request):
        await asyncio.sleep(5.0)
        return media_json()

    blizzard.media["slowpoke"] = slow
    await _seed(session_factory, as_user.tenant_id, ("self", "Slowpoke", "Draenor", "EU"))
    started = time.monotonic()
    assert await _portraits(as_user.client) == {"Slowpoke": None}
    assert time.monotonic() - started < 1.5  # the deadline, not the budget or the 5 s answer
    assert await _portraits(as_user.client) == {"Slowpoke": None}
    assert len(blizzard.media_requests) == 1  # the second load asked nobody
    ttl = await fake_redis.ttl(keys.char_portrait("eu", "draenor", "slowpoke"))
    assert 0 < ttl <= portraits.UNAVAILABLE_TTL_S * 1.1 + 1


def test_fetch_deadline_is_inside_the_budget():
    assert portraits.FETCH_DEADLINE_S < portraits.BUDGET_S


async def test_failed_token_fetch_backs_off(blizzard):
    """SEC-002: bad credentials cost one refused token request, not one per character."""
    blizzard.token_status = 401
    for name in ("Alpha", "Bravo", "Charlie"):
        assert await portraits.portrait_url(CharacterRef("eu", "Draenor", name)) is None
    assert [r.url.host for r in blizzard.requests] == ["oauth.battle.net"]


async def test_refused_token_is_replaced_once(blizzard):
    """SEC-002: a media 401 drops the token and retries once with a fresh one."""
    answers = [httpx.Response(401), media_json()]

    async def refuse_then_answer(request):
        return answers.pop(0)

    blizzard.media["traecie"] = refuse_then_answer
    assert await portraits.portrait_url(CharacterRef("eu", "Draenor", "Traecie")) == AVATAR
    hosts = [r.url.host for r in blizzard.requests]
    assert hosts == ["oauth.battle.net", "eu.api.blizzard.com", "oauth.battle.net", "eu.api.blizzard.com"]


async def test_token_refused_twice_is_unavailable(blizzard):
    blizzard.media["traecie"] = httpx.Response(401)
    assert await portraits.portrait_url(CharacterRef("eu", "Draenor", "Traecie")) is None
    assert len(blizzard.media_requests) == 2  # one retry, no loop


async def test_compressed_body_is_refused_and_identity_asked(blizzard):
    """SEC-005: the size cap counts raw bytes, so an encoded body (which could expand far past
    the cap) is refused, and both requests ask for an unencoded one."""
    import gzip

    blizzard.media["traecie"] = httpx.Response(
        200, content=gzip.compress(media_json().content), headers={"content-encoding": "gzip"}
    )
    assert await portraits.portrait_url(CharacterRef("eu", "Draenor", "Traecie")) is None
    assert all(r.headers["accept-encoding"] == "identity" for r in blizzard.requests)
