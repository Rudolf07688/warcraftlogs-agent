"""The suite never reads a checkout's .env; the app still does (feature 047, sc-336).

A sentinel .env sits in the working directory: neither the settings nor the process environment
may carry its values under tests. The app's own start (no switch) still loads it.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from backend.app import config

ROOT = pathlib.Path(__file__).resolve().parents[2]
SENTINEL = "sentinel-047-from-dotenv"
PROBE = (
    "import os, backend.app.config as c; "
    "print(os.environ.get('WCL_047_SENTINEL'), c.Settings().secret_key, sep='|')"
)


def _dotenv(folder: pathlib.Path) -> None:
    (folder / ".env").write_text(f"WCL_047_SENTINEL={SENTINEL}\nSECRET_KEY={SENTINEL}\n")


def test_the_suite_switches_dotenv_off():
    assert os.environ["WCL_LOAD_DOTENV"] == "0"
    assert config.LOAD_DOTENV is False
    assert config.Settings.model_config.get("env_file") is None


def test_settings_ignore_a_dotenv_in_the_working_directory(tmp_path, monkeypatch):
    _dotenv(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert config.Settings().secret_key != SENTINEL
    assert SENTINEL not in os.environ.values()


def _probe(cwd: pathlib.Path, **extra: str) -> str:
    env = {"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT)}
    out = subprocess.run(
        [sys.executable, "-c", PROBE], cwd=cwd, env={**env, **extra}, capture_output=True, text=True, timeout=120
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout.strip().splitlines()[-1]


def test_importing_the_app_with_the_switch_off_reads_no_dotenv(tmp_path):
    _dotenv(tmp_path)
    assert _probe(tmp_path, WCL_LOAD_DOTENV="0") == f"None|{config.Settings.model_fields['secret_key'].default}"


def test_the_app_still_loads_dotenv_without_the_switch(tmp_path):
    """AC4: docker, the dev server and the CLI set no switch, so .env is loaded as before."""
    _dotenv(tmp_path)
    assert _probe(tmp_path) == f"{SENTINEL}|{SENTINEL}"
