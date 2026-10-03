"""Delivery seam for invitation & password-reset links (feature 006, research R9).

v1 has **no email provider**: delivery is founder-mediated — the admin copies the
link from the API response and shares it manually. This module is the single seam so
an email implementation can drop in later behind the same functions without touching
callers (spec FR-007, FR-025).

Security invariants:
- Links are built from the **trusted** canonical ``settings.site_url`` — NEVER from the
  inbound ``Host`` header (which an attacker controls).
- The raw token goes in the URL **fragment** (``#token=…``), not the query string, so it
  never reaches server logs or the ``Referer`` header. The frontend reads it once and
  strips it via ``history.replaceState`` (research R9).
- The raw token is returned to the admin **once** at create/resend/trigger-reset; it is
  never stored in raw form and never exposed by any list view.
"""

from __future__ import annotations

from ..config import settings


def build_invite_link(raw_token: str) -> str:
    """Canonical single-use invitation link with the raw token in the fragment."""
    return f"{settings.site_url.rstrip('/')}/accept-invite#token={raw_token}"


def build_reset_link(raw_token: str) -> str:
    """Canonical single-use password-reset link with the raw token in the fragment."""
    return f"{settings.site_url.rstrip('/')}/reset-password#token={raw_token}"


async def deliver_invitation_link(*, email: str, raw_token: str) -> str:
    """Deliver an invitation link.

    v1: performs no send; returns the link for the admin to copy & share. A future
    email implementation sends here and may still return the link (or ``""``) — the
    admin UI shows whatever is returned.
    """
    return build_invite_link(raw_token)


async def deliver_reset_link(*, email: str, raw_token: str) -> str:
    """Deliver a password-reset link (v1: founder-mediated, same as invitations)."""
    return build_reset_link(raw_token)
