"""Team token counter (.claude/team/tokens.py): the chat request as the app builds it, offline."""
from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from backend.tests.test_064_prompt_budget import CLAUDE, GEMINI, _request, _schema_chars

TOKENS = Path(__file__).resolve().parents[2] / ".claude" / "team" / "tokens.py"


def _module():
    spec = importlib.util.spec_from_file_location("team_tokens", TOKENS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("tokens.py made a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.mark.parametrize("model", [GEMINI, CLAUDE])
async def test_measures_the_request_the_budget_test_measures_without_network(model, no_network):
    parts = await _module().measure(model)
    agent, request = await _request(model)
    assert parts["instruction"] == len(agent.instruction(None))
    assert parts["tool schemas"] == _schema_chars(model, request)
    assert parts["history"] == parts["message"] == 0


@pytest.mark.parametrize("model", [GEMINI, CLAUDE])
async def test_history_and_message_count_their_wire_size(model, no_network):
    tokens = _module()
    history = [{"role": "user", "text": "how did we do?"}, {"role": "model", "text": "8/8, 3 wipes"}]
    short = await tokens.measure(model, history, "why?")
    long = await tokens.measure(model, history, "why?" * 100)
    assert short["history"] > len("how did we do?8/8, 3 wipes")
    assert long["message"] - short["message"] == len("why?") * 99


@pytest.mark.parametrize("spelling", [["--history=h.json"], ["--hist=h.json"], ["--history", "h.json"]])
def test_cli_history_option_spellings_reach_the_measurement(tmp_path: Path, spelling: list[str]) -> None:
    """BUG-008: `--history=FILE` crashed the wrapper (it looked the bare path up in argv). The file
    is relative to where the caller stands, but the measuring run starts in the repo root."""
    (tmp_path / "h.json").write_text(json.dumps([{"role": "user", "text": "x" * 500}]))
    r = subprocess.run([sys.executable, str(TOKENS), "--model", GEMINI, "--json", *spelling],
                       cwd=tmp_path, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["models"][GEMINI]["history"]["chars"] > 500


def test_cli_labels_tokens_as_an_estimate(tmp_path: Path) -> None:
    r = subprocess.run([sys.executable, str(TOKENS), "--model", GEMINI, "--json"], cwd=tmp_path,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["estimate"] == "chars/4"
    part = out["models"][GEMINI]["instruction"]
    assert part["tokens"] == round(part["chars"] / 4) > 0
