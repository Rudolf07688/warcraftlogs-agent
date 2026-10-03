"""CSPRNG secret tokens + sha256 digests (feature 006, research R3).

Pattern for every single-use/bearer secret (session, CSRF, invitation, reset):
generate a high-entropy random token, hand the RAW token to the client once, and store
ONLY its sha256 digest. Lookups query by digest; sensitive comparisons use a
constant-time compare. The raw token is never written to a database column, log, or
audit record (FR-002, FR-030).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from ..config import settings


def generate_token() -> str:
    """Return a URL-safe, unpadded base64 random token (suitable for a URL fragment)."""
    raw = secrets.token_bytes(settings.token_entropy_bytes)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def hash_token(raw_token: str) -> bytes:
    """sha256 digest (32 raw bytes) of a token, as stored in ``*_hash`` columns."""
    return hashlib.sha256(raw_token.encode("utf-8")).digest()


def tokens_equal(a: bytes, b: bytes) -> bool:
    """Constant-time comparison of two digests (use for CSRF checks)."""
    return hmac.compare_digest(a, b)
