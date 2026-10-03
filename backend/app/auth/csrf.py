"""CSRF protection for unsafe requests (feature 006, research R3).

Defense is two-layered and both must pass on every state-changing request:
1. A per-session CSRF token the SPA sends as ``X-CSRF-Token``. The token is HMAC-derived
   from the session id (``HMAC(secret_key, session_id)``), so it is **stateless** — the
   server recomputes it on every ``/me`` (a page reload recovers it) without storing it,
   and it's identical across tabs. An attacker can't forge it without ``secret_key``, and
   can't read it cross-origin (SameSite + no CORS credentials).
2. An ``Origin``/``Referer`` check against the canonical site origin.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid

from fastapi import Request

from ..config import settings

CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def issue_csrf(session_id: uuid.UUID) -> str:
    """Deterministic CSRF token for a session (HMAC of the session id)."""
    mac = hmac.new(
        settings.secret_key.encode("utf-8"), str(session_id).encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


def verify_csrf(session_id: uuid.UUID, provided: str | None) -> bool:
    """Constant-time check that a provided token matches this session's HMAC token."""
    if not provided:
        return False
    return hmac.compare_digest(issue_csrf(session_id), provided)


def _allowed_origins() -> set[str]:
    return {settings.site_url.rstrip("/")}


def origin_matches(origin: str | None) -> bool:
    """True iff an Origin header value matches the canonical origin (WS handshake uses this)."""
    return bool(origin) and origin.rstrip("/") in _allowed_origins()


def is_origin_allowed(request: Request) -> bool:
    """True iff a present ``Origin``/``Referer`` matches the canonical origin.

    Fails closed: a state-changing request with neither header is rejected.
    """
    allowed = _allowed_origins()
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/") in allowed
    referer = request.headers.get("referer")
    if referer:
        return any(referer.rstrip("/") == o or referer.startswith(o + "/") for o in allowed)
    return False
