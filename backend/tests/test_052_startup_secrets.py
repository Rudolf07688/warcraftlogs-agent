"""No silent start on the dev secret (feature 052, sc-356).

With the dev secret key and a public site that isn't localhost, startup fails with a clear
message; local dev and the suite start as before; a warning names each insecure default in use
(secret key, database URL) without printing a value.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI

from backend.app import main
from backend.app.config import Settings, check_startup_secrets, settings

STRONG = "x" * 48


@pytest.fixture(autouse=True)
def built_in_defaults(monkeypatch):
    """Settings() below read their defaults, whatever the environment running the suite sets."""
    for name in ("SECRET_KEY", "DATABASE_URL", "SITE_URL"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    "site", ["https://wcl.example.org", "http://192.168.1.20:5173", "http://10.0.0.5", "localhost:5173"]
)
def test_the_dev_secret_on_a_public_site_refuses_to_start(site):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        check_startup_secrets(Settings(site_url=site))


def test_a_secret_set_to_the_dev_value_counts_as_the_default():
    with pytest.raises(RuntimeError):
        check_startup_secrets(
            Settings(site_url="https://wcl.example.org", secret_key="dev-insecure-change-me")
        )


@pytest.mark.parametrize("secret", ["", "   ", "short-but-random-1234", "please-change-me-" + "x" * 32])
def test_an_empty_short_or_placeholder_secret_counts_as_insecure(secret):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        check_startup_secrets(Settings(site_url="https://wcl.example.org", secret_key=secret))


@pytest.mark.parametrize(
    "site",
    [
        "http://evil.org\\@localhost:5173",  # Python reads localhost, a browser evil.org
        "http://evil.org\\localhost",
        "http://user@localhost:5173",
        "ftp://localhost",
        "//localhost:5173",
    ],
)
def test_a_site_only_python_reads_as_local_is_not_local(site):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        check_startup_secrets(Settings(site_url=site))


@pytest.mark.parametrize(
    "site", ["http://localhost:5173", "http://127.0.0.1:8000", "http://[::1]:5173", "http://LOCALHOST"]
)
def test_local_dev_starts_on_the_dev_secret(site):
    check_startup_secrets(Settings(site_url=site))


def test_a_real_secret_starts_anywhere(caplog):
    with caplog.at_level(logging.WARNING):
        check_startup_secrets(Settings(site_url="https://wcl.example.org", secret_key=STRONG,
                                       database_url="postgresql+asyncpg://app:pw@db:5432/wcl"))
    assert "insecure" not in caplog.text


def test_the_warning_names_each_default_without_values(caplog):
    with caplog.at_level(logging.WARNING):
        check_startup_secrets(Settings(site_url="http://localhost:5173"))
    assert "SECRET_KEY" in caplog.text and "DATABASE_URL" in caplog.text
    assert "dev-insecure-change-me" not in caplog.text and "wcl:wcl" not in caplog.text


def test_only_the_defaults_in_use_are_named(caplog):
    with caplog.at_level(logging.WARNING):
        check_startup_secrets(Settings(site_url="http://localhost:5173", secret_key=STRONG))
    assert "DATABASE_URL" in caplog.text and "SECRET_KEY" not in caplog.text


async def test_the_app_lifespan_runs_the_check_first(monkeypatch):
    monkeypatch.setattr(settings, "site_url", "https://wcl.example.org")
    monkeypatch.setattr(settings, "secret_key", "dev-insecure-change-me")
    started: list[str] = []
    monkeypatch.setattr(main, "KbIndexer", lambda **_: started.append("kb"))
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        async with main.lifespan(FastAPI()):
            pass
    assert started == []  # nothing was started before the refusal
