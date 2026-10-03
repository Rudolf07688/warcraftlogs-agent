"""US2/polish: progressive login throttling + token-endpoint caps (T062)."""

from __future__ import annotations

from backend.app.auth.rate_limit import InProcessRateLimiter


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
