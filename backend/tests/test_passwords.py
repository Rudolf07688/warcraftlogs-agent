"""Unit tests for Argon2id hashing + password policy (T010)."""

from __future__ import annotations

import pytest

from backend.app.auth import passwords


def test_policy_rejects_too_short():
    with pytest.raises(passwords.PasswordPolicyError):
        passwords.validate_password_policy("short")


def test_policy_rejects_common_and_trivial():
    with pytest.raises(passwords.PasswordPolicyError):
        passwords.validate_password_policy("aaaaaaaaaaaaaaaa")  # single repeated char


def test_policy_accepts_strong():
    passwords.validate_password_policy("correct horse battery staple 42")


async def test_hash_and_verify_roundtrip():
    h = await passwords.hash_password("correct horse battery staple 42")
    assert h and h != "correct horse battery staple 42"
    ok, updated = await passwords.verify_password("correct horse battery staple 42", h)
    assert ok is True
    # Fresh recommended params shouldn't need an immediate rehash.
    assert updated is None


async def test_verify_wrong_password_fails():
    h = await passwords.hash_password("correct horse battery staple 42")
    ok, _ = await passwords.verify_password("wrong password entirely!!", h)
    assert ok is False


async def test_verify_against_missing_hash_is_false():
    # Unknown-email / un-activated path: verifies against dummy, returns False.
    ok, updated = await passwords.verify_password("anything at all here", None)
    assert ok is False
    assert updated is None
