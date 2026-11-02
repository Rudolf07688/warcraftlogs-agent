"""One round trip for the tenant scope; TRUSTED_PROXIES parsed once (feature 052, sc-270).

The Postgres behaviour (RLS still applies with both settings from one statement) is covered by
the unchanged RLS suites under ``check.py run --pg``.
"""

from __future__ import annotations

import ipaddress
import uuid
from types import SimpleNamespace

import pytest

from backend.app import config
from backend.app.config import Settings, settings
from backend.app.tenancy.context import set_scope


class _PgSession:
    """Just enough of an AsyncSession on Postgres to record what set_scope sends."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, dict]] = []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    async def execute(self, statement, params=None):
        self.executed.append((str(statement), params))


async def test_both_settings_go_in_one_statement():
    session, tenant, user = _PgSession(), uuid.uuid4(), uuid.uuid4()
    await set_scope(session, tenant_id=tenant, user_id=user)
    assert len(session.executed) == 1
    statement, params = session.executed[0]
    assert "set_config('app.tenant_id'" in statement and "set_config('app.user_id'" in statement
    assert statement.count("true)") == 2  # both transaction-local
    assert params == {"tid": str(tenant), "uid": str(user)}


async def test_no_identity_sets_both_empty():
    session = _PgSession()
    await set_scope(session, tenant_id=None)
    assert session.executed[0][1] == {"tid": "", "uid": ""}


async def test_sqlite_sends_nothing(session_factory):
    async with session_factory() as session:
        recorded = _PgSession()
        session.execute = recorded.execute  # type: ignore[method-assign]
        await set_scope(session, tenant_id=uuid.uuid4(), user_id=uuid.uuid4())
    assert recorded.executed == []


def test_trusted_proxies_are_parsed_once(monkeypatch):
    calls = {"n": 0}
    real = ipaddress.ip_network

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(config.ipaddress, "ip_network", counting)
    s = Settings(trusted_proxies="10.1.0.0/16, 192.0.2.7")
    calls["n"] = 0
    first = s.trusted_proxy_networks
    for _ in range(5):
        assert s.trusted_proxy_networks == first
    assert calls["n"] <= 2  # one parse of the two entries (the validator may have done it)
    assert first == (ipaddress.ip_network("10.1.0.0/16"), ipaddress.ip_network("192.0.2.7/32"))


def test_a_changed_value_is_parsed_again(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", "10.0.0.0/8")
    assert settings.trusted_proxy_networks == (ipaddress.ip_network("10.0.0.0/8"),)
    monkeypatch.setattr(settings, "trusted_proxies", "")
    assert settings.trusted_proxy_networks == ()


def test_the_parsed_list_cannot_be_changed_by_a_caller():
    with pytest.raises(AttributeError):
        Settings(trusted_proxies="10.0.0.0/8").trusted_proxy_networks.append(None)  # type: ignore[attr-defined]
