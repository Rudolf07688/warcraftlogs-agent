"""US2/polish: progressive login throttling + token-endpoint caps (T062)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from backend.app.auth.rate_limit import InProcessRateLimiter, client_source
from backend.app.config import Settings, settings


def test_progressive_block_after_threshold_then_reset():
    rl = InProcessRateLimiter(failure_threshold=3, max_delay_s=30, per_minute=100)
    # Below threshold: no block.
    rl.record_failure("k")
    rl.record_failure("k")
    assert rl.retry_after("k") == 0.0
    # At/over threshold: a (capped) delay kicks in.
    rl.record_failure("k")
    assert rl.retry_after("k") > 0.0
    # Success clears it (never a permanent lockout).
    rl.record_success("k")
    assert rl.retry_after("k") == 0.0


def test_delay_is_capped():
    rl = InProcessRateLimiter(failure_threshold=1, max_delay_s=5, per_minute=100)
    for _ in range(20):
        rl.record_failure("k")
    assert rl.retry_after("k") <= 5.0  # capped, not unbounded


def test_fixed_window_per_minute_cap():
    rl = InProcessRateLimiter(per_minute=3)
    assert [rl.allow_request("src") for _ in range(4)] == [True, True, True, False]


async def test_login_throttles_and_does_not_distinguish_known_vs_unknown(client):
    # Unknown account: repeated failures still eventually throttle (no enumeration signal).
    email = "throttle-me@example.com"
    statuses = []
    for _ in range(8):
        r = await client.post("/api/auth/login", json={"email": email, "password": "wrong-pass-123456"})
        statuses.append(r.status_code)
    assert 429 in statuses  # progressive throttle engaged
    assert set(statuses) <= {401, 429}  # only generic failure / throttle, never a distinct signal


# --- sc-158: the per-source key behind a reverse proxy -------------------------------


def _request(peer: str | None, *forwarded: str) -> Request:
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded]
    scope = {"type": "http", "headers": headers, "client": (peer, 1234) if peer else None}
    return Request(scope)


@pytest.mark.parametrize(
    ("trusted", "peer", "forwarded", "expected"),
    [
        # Default: trust nothing, forwarded headers ignored (behaviour unchanged).
        ("", "203.0.113.9", ("198.51.100.1",), "203.0.113.9"),
        ("", "10.0.0.2", (), "10.0.0.2"),
        # A spoofed header from a peer that isn't a trusted proxy is ignored.
        ("10.0.0.0/8", "203.0.113.9", ("198.51.100.1",), "203.0.113.9"),
        # Trusted proxy: the client it saw.
        ("10.0.0.0/8", "10.0.0.2", ("198.51.100.1",), "198.51.100.1"),
        # Trusted proxy, header missing: the proxy itself.
        ("10.0.0.0/8", "10.0.0.2", (), "10.0.0.2"),
        # Client-written entries left of the real one don't count (rightmost untrusted).
        ("10.0.0.0/8", "10.0.0.2", ("1.2.3.4, 198.51.100.1",), "198.51.100.1"),
        # A chain of trusted proxies, split over two header lines.
        ("10.0.0.0/8,127.0.0.1", "127.0.0.1", ("198.51.100.1, 10.0.0.5", "10.0.0.7"), "198.51.100.1"),
        # Only trusted hops: the outermost one.
        ("10.0.0.0/8", "10.0.0.2", ("10.0.0.5",), "10.0.0.5"),
        # Garbage where the client should be: keep the peer key.
        ("10.0.0.0/8", "10.0.0.2", ("not-an-ip",), "10.0.0.2"),
        ("::1", "::1", ("2001:db8::7",), "2001:db8::7"),
        ("10.0.0.0/8", None, ("198.51.100.1",), "unknown"),
    ],
)
def test_client_source(monkeypatch, trusted, peer, forwarded, expected):
    monkeypatch.setattr(settings, "trusted_proxies", trusted)
    assert client_source(_request(peer, *forwarded)) == expected


def test_a_bad_trusted_proxy_entry_fails_at_startup():
    with pytest.raises(ValidationError):
        Settings(trusted_proxies="10.0.0.0/8,not-a-network")


async def _login_statuses(client, email: str, forwarded: list[str]) -> list[int]:
    statuses = []
    for xff in forwarded:
        r = await client.post(
            "/api/auth/login",
            json={"email": email, "password": "wrong-pass-123456"},
            headers={"x-forwarded-for": xff},
        )
        statuses.append(r.status_code)
    return statuses


async def test_login_buckets_per_forwarded_client_behind_a_trusted_proxy(client, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", "127.0.0.1")  # the test transport's peer
    email = "behind-proxy@example.com"
    assert 429 in await _login_statuses(client, email, ["198.51.100.1"] * 8)
    # Another client behind the same proxy has its own bucket.
    assert await _login_statuses(client, email, ["198.51.100.2"]) == [401]


async def test_login_ignores_spoofed_forwarded_for_from_an_untrusted_peer(client, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", "")
    # A fresh fake address per attempt doesn't escape the throttle.
    spoofed = [f"198.51.100.{i}" for i in range(10, 18)]
    assert 429 in await _login_statuses(client, "spoofer@example.com", spoofed)
