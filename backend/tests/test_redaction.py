"""Unit tests for log redaction (T012)."""

from __future__ import annotations

from backend.app.auth.redaction import REDACTED, is_sensitive_key, redact


def test_is_sensitive_key_matches_variants():
    for k in ("password", "Password", "csrf_token", "Set-Cookie", "Authorization"):
        assert is_sensitive_key(k)
    for k in ("email", "user_id", "name"):
        assert not is_sensitive_key(k)


def test_redact_nested_dict():
    data = {
        "email": "a@b.c",
        "password": "hunter2",
        "nested": {"csrf_token": "abc", "keep": 1},
        "list": [{"token": "zzz"}, {"ok": True}],
    }
    out = redact(data)
    assert out["email"] == "a@b.c"
    assert out["password"] == REDACTED
    assert out["nested"]["csrf_token"] == REDACTED
    assert out["nested"]["keep"] == 1
    assert out["list"][0]["token"] == REDACTED
    assert out["list"][1]["ok"] is True
    # Original is not mutated.
    assert data["password"] == "hunter2"
