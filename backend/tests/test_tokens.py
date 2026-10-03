"""Unit tests for token generation, digests, and constant-time compare (T011)."""

from __future__ import annotations

import base64

from backend.app.auth import tokens


def test_generate_token_is_urlsafe_and_unique():
    a = tokens.generate_token()
    b = tokens.generate_token()
    assert a != b
    assert "=" not in a  # unpadded
    assert "+" not in a and "/" not in a  # url-safe alphabet
    # Decodes back to the configured entropy width.
    decoded = base64.urlsafe_b64decode(a + "=" * (-len(a) % 4))
    assert len(decoded) >= 32


def test_hash_token_is_deterministic_32_bytes():
    raw = tokens.generate_token()
    d1 = tokens.hash_token(raw)
    d2 = tokens.hash_token(raw)
    assert d1 == d2
    assert isinstance(d1, bytes) and len(d1) == 32


def test_hash_token_differs_per_input():
    assert tokens.hash_token("a") != tokens.hash_token("b")


def test_tokens_equal_constant_time():
    raw = tokens.generate_token()
    assert tokens.tokens_equal(tokens.hash_token(raw), tokens.hash_token(raw))
    assert not tokens.tokens_equal(tokens.hash_token("x"), tokens.hash_token("y"))
