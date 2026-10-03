"""Argon2id password hashing + policy validation (feature 006, research R2).

Hashing/verification is CPU-bound, so it runs off the event loop via
``anyio.to_thread.run_sync`` under a bounded semaphore — it never blocks the loop and
a login flood cannot exhaust CPU/memory (Principle V; guide §Password hashing).

Login against an unknown email verifies against a process-level **dummy** hash so the
response time matches the real path and attackers cannot enumerate accounts by timing.
"""

from __future__ import annotations

import asyncio

import anyio
from pwdlib import PasswordHash

from ..config import settings

_hasher = PasswordHash.recommended()
_semaphore = asyncio.Semaphore(settings.password_hash_max_concurrency)

# Computed once at import so the unknown-email login path has a real hash to verify
# against (constant-time vs. the existing-user path). The value is irrelevant.
_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time-login-xyzzy")

# A tiny built-in blocklist of trivially-guessed passwords. Not a full breach corpus
# (that would be heavy infra, YAGNI); it just rejects the most obvious choices.
_COMMON = frozenset(
    {
        "password",
        "passw0rd",
        "123456789012345",
        "qwertyuiopasdfg",
        "administrator00",
        "letmeinletmein0",
    }
)


class PasswordPolicyError(ValueError):
    """Raised when a candidate password violates policy. Message is user-safe and
    never echoes the password itself (FR-002)."""


def validate_password_policy(password: str) -> None:
    """Enforce length + obvious-weakness policy. Raises ``PasswordPolicyError``."""
    if len(password) < settings.password_min_length:
        raise PasswordPolicyError(
            f"Password must be at least {settings.password_min_length} characters."
        )
    if len(password) > settings.password_max_length:
        raise PasswordPolicyError(
            f"Password must be at most {settings.password_max_length} characters."
        )
    lowered = password.lower()
    if lowered in _COMMON:
        raise PasswordPolicyError("Password is too common; choose something less guessable.")
    if len(set(password)) == 1:
        raise PasswordPolicyError("Password is too simple; choose something less guessable.")


async def hash_password(password: str) -> str:
    """Hash a password with Argon2id, off the event loop."""
    async with _semaphore:
        return await anyio.to_thread.run_sync(_hasher.hash, password)


async def verify_password(password: str, password_hash: str | None) -> tuple[bool, str | None]:
    """Verify a password against a stored hash.

    Returns ``(is_valid, updated_hash)``. ``updated_hash`` is a fresh hash to persist
    when the stored parameters are outdated (rehash-on-login), else ``None``. When
    ``password_hash`` is ``None`` (unknown email / un-activated user), verifies against
    the dummy hash to equalize timing and returns ``(False, None)``.
    """
    if not password_hash:
        await _verify_dummy(password)
        return (False, None)
    async with _semaphore:
        return await anyio.to_thread.run_sync(_hasher.verify_and_update, password, password_hash)


async def _verify_dummy(password: str) -> None:
    async with _semaphore:
        await anyio.to_thread.run_sync(_hasher.verify, password, _DUMMY_HASH)
