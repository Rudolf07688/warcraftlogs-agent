"""Character portraits from the Blizzard Profile API (feature 075, sc-363).

A character's small "avatar" image comes from the character-media endpoint, read with the app's
client-credentials token. Every outcome is cached in the shared Redis cache (family
``char_portrait``, tenant-less: portraits are public): a found portrait for a day, "no such
character / no portrait" for hours, a failure for minutes, so a page load inside those windows
never calls Blizzard. Nothing here raises to the caller: any problem is "no portrait".

Guards (spec Edge Cases): the host is fixed per allow-listed region; realm slug and name are
allow-listed shapes and each one encoded path segment; no redirect is followed and the body
read is capped; only https URLs on Blizzard's render host are kept, checked when stored and
again when served. The access token lives in process memory only; it and the client secret
never reach a log, an error, the cache or a response.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import unicodedata
import weakref
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel

from wcl_agent.cache.cache import CacheFamily, family_ttl, get_or_load, keys
from wcl_agent.cache.normalize import server_slug

from ..config import settings

logger = logging.getLogger(__name__)

REGIONS = frozenset({"eu", "us", "kr", "tw"})  # cn is a different service: no portraits
RENDER_HOSTS = frozenset({"render.worldofwarcraft.com"})  # live-check:075-pre (#94)
TOKEN_URL = "https://oauth.battle.net/token"

HTTP_TIMEOUT_S = 3.0
MAX_BODY_BYTES = 64 * 1024  # a media answer is ~1 KiB; anything bigger is not one
BUDGET_S = 4.0  # the endpoint waits at most this; unfinished lookups are null this time
CONCURRENCY = 6
NONE_TTL_S = 6 * 3600  # not found, private, or no avatar asset
UNAVAILABLE_TTL_S = 300  # Blizzard down, rate limiting, slow, or an answer we can't read
_TOKEN_MARGIN_S = 60
_MAX_NAME = 24
_MAX_SLUG = 64
_MAX_URL = 512

_SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True)
class CharacterRef:
    """A character's identity as stored in the profile (region, realm and name as typed)."""

    region: str
    realm: str
    name: str


class PortraitCache(BaseModel):
    """The cached outcome of one lookup. ``url`` is set only when ``status`` is found."""

    status: Literal["found", "none", "unavailable"]
    url: str | None = None


def _ttl(value: PortraitCache) -> int:
    if value.status == "found":
        return family_ttl(CacheFamily.CHAR_PORTRAIT)
    return NONE_TTL_S if value.status == "none" else UNAVAILABLE_TTL_S


# --- input shapes (allow-lists: anything else makes no request) ----------------------------


def region_of(raw: str) -> str | None:
    region = raw.strip().lower()
    return region if region in REGIONS else None


def realm_slug(raw: str) -> str | None:
    """Blizzard's realm slug: ``"Aggra (Português)"`` → ``"aggra-portugues"``. None if the
    result isn't plain ``a-z0-9`` words joined by hyphens."""
    slug = unicodedata.normalize("NFKD", server_slug(raw))
    slug = "".join(ch for ch in slug if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-z0-9-]+", "", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug if len(slug) <= _MAX_SLUG and _SLUG_RE.fullmatch(slug) else None


def char_name(raw: str) -> str | None:
    """A character name is letters only (any script). Lower case, as Blizzard's path wants."""
    name = raw.strip().lower()
    return name if 0 < len(name) <= _MAX_NAME and name.isalpha() else None


def media_url(region: str, slug: str, name: str) -> str:
    """The character-media URL: fixed host per region, each part one encoded path segment."""
    return (
        f"https://{region}.api.blizzard.com/profile/wow/character/"
        f"{quote(slug, safe='')}/{quote(name, safe='')}/character-media"
    )


def safe_image_url(raw: object) -> str | None:
    """``raw`` if it is an https URL on Blizzard's render host, else None. The netloc must be
    exactly the host: no userinfo, port or backslash a browser would read differently."""
    if not isinstance(raw, str) or len(raw) > _MAX_URL:
        return None
    if "\\" in raw or any(ch.isspace() or not ch.isprintable() for ch in raw):
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.netloc not in RENDER_HOSTS or not parts.path.startswith("/"):
        return None
    return raw


# --- Blizzard calls --------------------------------------------------------------------------


def _http_client() -> httpx.AsyncClient:
    # Tests replace this to inject a fake transport. Redirects are never followed.
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT_S, follow_redirects=False)


async def _read_json(response: httpx.Response) -> object:
    """The body as JSON, read at most :data:`MAX_BODY_BYTES`; ValueError when bigger or bad."""
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            raise ValueError("response body too large")
    return json.loads(bytes(body))


class _Unavailable(Exception):
    """Blizzard couldn't answer usefully; carries a short reason, never a token or URL."""


_tokens: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, tuple[str, float]] = weakref.WeakKeyDictionary()
_token_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = weakref.WeakKeyDictionary()


def configured() -> bool:
    return bool(settings.blizzard_client_id and settings.blizzard_client_secret.get_secret_value())


async def _access_token(client: httpx.AsyncClient) -> str:
    """The client-credentials token, fetched once per loop and reused until near its expiry."""
    loop = asyncio.get_running_loop()
    lock = _token_locks.setdefault(loop, asyncio.Lock())
    async with lock:
        cached = _tokens.get(loop)
        if cached is not None and time.monotonic() < cached[1]:
            return cached[0]
        secret = settings.blizzard_client_secret.get_secret_value()
        async with client.stream(
            "POST",
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(settings.blizzard_client_id, secret),
        ) as response:
            if response.status_code != 200:
                raise _Unavailable(f"token status {response.status_code}")
            try:
                body = await _read_json(response)
            except ValueError:
                raise _Unavailable("token answer unreadable") from None
        token = body.get("access_token") if isinstance(body, dict) else None
        expires = body.get("expires_in") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            raise _Unavailable("token answer without a token")
        ttl = expires if isinstance(expires, int) and expires > 0 else 3600
        _tokens[loop] = (token, time.monotonic() + max(ttl - _TOKEN_MARGIN_S, 1))
        return token


def _avatar(body: object) -> str | None:
    assets = body.get("assets") if isinstance(body, dict) else None
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if isinstance(asset, dict) and asset.get("key") == "avatar":
            return safe_image_url(asset.get("value"))
    return None


async def _fetch(region: str, slug: str, name: str) -> PortraitCache:
    """One character-media lookup. Never raises: failures are an "unavailable" outcome."""
    try:
        async with _http_client() as client:
            token = await _access_token(client)
            async with client.stream(
                "GET",
                media_url(region, slug, name),
                params={"namespace": f"profile-{region}", "locale": "en_US"},
                headers={"Authorization": f"Bearer {token}"},
            ) as response:
                if response.status_code in (403, 404):
                    return PortraitCache(status="none")
                if response.status_code != 200:
                    raise _Unavailable(f"media status {response.status_code}")
                try:
                    body = await _read_json(response)
                except ValueError:
                    raise _Unavailable("media answer unreadable") from None
    except _Unavailable as exc:
        logger.info("portrait lookup unavailable: %s", exc)
        return PortraitCache(status="unavailable")
    except httpx.HTTPError as exc:
        # The class name only: an httpx message can carry the request URL, never the token.
        logger.info("portrait lookup unavailable: %s", type(exc).__name__)
        return PortraitCache(status="unavailable")
    url = _avatar(body)
    return PortraitCache(status="found", url=url) if url else PortraitCache(status="none")


async def portrait_url(char: CharacterRef) -> str | None:
    """The character's avatar URL, from the cache or Blizzard; None for no portrait."""
    region, slug, name = region_of(char.region), realm_slug(char.realm), char_name(char.name)
    if region is None or slug is None or name is None or not configured():
        return None
    try:
        cached = await get_or_load(
            CacheFamily.CHAR_PORTRAIT,
            keys.char_portrait(region, slug, name),
            PortraitCache,
            lambda: _fetch(region, slug, name),
            ttl=_ttl,
        )
    except Exception:  # noqa: BLE001 - a portrait is decoration: never fail the request
        logger.exception("portrait lookup failed")
        return None
    return safe_image_url(cached.url) if cached is not None and cached.status == "found" else None


async def portrait_urls(chars: Sequence[CharacterRef]) -> list[str | None]:
    """Each character's portrait URL, in order, looked up concurrently (at most
    :data:`CONCURRENCY` at once) within :data:`BUDGET_S`; one still running then is None."""
    if not chars:
        return []
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(char: CharacterRef) -> str | None:
        async with gate:
            return await portrait_url(char)

    tasks = [asyncio.ensure_future(one(c)) for c in chars]
    done, pending = await asyncio.wait(tasks, timeout=BUDGET_S)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    return [t.result() if t in done and not t.cancelled() else None for t in tasks]
