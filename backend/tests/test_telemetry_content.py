"""Feature 054 (sc-406): content capture is on in dev only, and secrets never leave.

A real ADK turn (``agent_runner.stream_response`` on ``build_agent``) on a scripted Claude API:
the model calls a tool with an argument, the tool answers, the model answers. Prompt, argument,
tool result and answer carry sentinels; the tool result and answer also carry secrets. The
exporters are in-memory, behind the production redaction wrappers.
"""

from __future__ import annotations

import pytest

from backend.app import agent_runner
from backend.app.telemetry import policy
from backend.app.telemetry.config import load_config
from backend.tests.test_llm_provider_agent import (  # noqa: F401 - fixture
    CLAUDE,
    SENTINEL_KEY,
    ScriptedApi,
    text_answer,
    use_provider,
)
from backend.tests.test_telemetry_support import everything, otel, scripted_agent, tool_call_with  # noqa: F401

PROMPT = "PROMPT-SENTINEL-054 how did my raid go"
ARGUMENT = "ARG-SENTINEL-054"
RESULT = "RESULT-SENTINEL-054"
ANSWER = "ANSWER-SENTINEL-054 it went well"
SECRET_TOKEN = "tok-SECRET-054-abcdef"
SECRET_KEY = "sk-ant-api03-SECRET054SECRET054SECRET"
SENTINELS = ("PROMPT-SENTINEL-054", ARGUMENT, RESULT, "ANSWER-SENTINEL-054")


async def lookup_report(code: str) -> dict:
    """Look up a report by its code."""
    return {"code": code, "summary": RESULT, "access_token": SECRET_TOKEN}


def _tool_call_with_argument() -> bytes:
    return tool_call_with("lookup_report", {"code": ARGUMENT})


@pytest.fixture
def turn(monkeypatch, use_provider):
    """Run one scripted turn: tool call with an argument, then an answer that leaks a key."""
    use_provider("anthropic", key=SENTINEL_KEY)
    scripted_agent(
        monkeypatch,
        ScriptedApi(_tool_call_with_argument(), text_answer(f"{ANSWER} Bearer {SECRET_KEY}")),
        lookup_report,
    )

    async def run() -> list[dict]:
        records = [r async for r in agent_runner.stream_response(CLAUDE, "s-054", PROMPT)]
        assert [r["name"] for r in records if r["type"] == "tool_end"] == ["lookup_report"]
        return records

    return run


async def test_dev_exports_prompt_answer_and_tool_io_marked_as_content(otel, turn):
    capture = otel(environment="dev")
    await turn()

    exported = everything(capture)
    for sentinel in SENTINELS:
        assert sentinel in exported, sentinel
    names = {span.name.split(" ")[0] for span in capture.spans()}
    assert {"invoke_agent", "generate_content", "execute_tool"} <= names
    content_logs = [r.log_record for r in capture.logs() if (r.log_record.event_name or "").startswith("gen_ai.")]
    assert content_logs, "ADK emits its content as gen_ai.* log events in dev"
    assert all((log.attributes or {}).get(policy.CONTENT_FLAG) == "true" for log in content_logs)


@pytest.mark.parametrize("environment", ["ci", "prod", "unknown"])
async def test_outside_dev_no_content_leaves_the_process(otel, turn, environment, monkeypatch):
    monkeypatch.setenv("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "true")  # the lockdown overrides it
    capture = otel(environment=environment)
    await turn()

    spans = capture.spans()
    assert {"invoke_agent", "generate_content", "execute_tool"} <= {s.name.split(" ")[0] for s in spans}
    exported = everything(capture)
    for sentinel in SENTINELS:
        assert sentinel not in exported, (environment, sentinel)
    assert not [r for r in capture.logs() if (r.log_record.event_name or "").startswith("gen_ai.")]


async def test_secrets_are_masked_even_with_content_on(otel, turn):
    capture = otel(environment="dev")
    await turn()

    exported = everything(capture)
    assert RESULT in exported and "ANSWER-SENTINEL-054" in exported  # content is on...
    assert SECRET_TOKEN not in exported  # ...the tool's token is not
    assert SECRET_KEY not in exported  # ...nor the key in the answer
    assert SENTINEL_KEY not in exported  # ...nor the provider's API key


async def test_token_counts_survive_the_token_key_rule(otel, turn):
    capture = otel(environment="dev")
    await turn()

    usage = [
        value
        for span in capture.spans()
        for key, value in (span.attributes or {}).items()
        if key.startswith("gen_ai.usage.") and key.endswith("tokens")
    ]
    assert usage and all(isinstance(value, int) for value in usage)


# --- each half of the policy holds on its own ---------------------------------------------


async def test_adk_lockdown_alone_keeps_content_off_the_spans(otel, turn):
    capture = otel(environment="prod", exporter_content=True)  # wrappers would let it through
    await turn()

    for span in capture.spans():
        content = {v for k, v in (span.attributes or {}).items() if policy.is_content_attribute(k)}
        assert content <= {"{}"}, span.name  # ADK's placeholder for "not captured"
    assert not any(s in everything(capture) for s in SENTINELS)


async def test_the_exporter_wrappers_alone_strip_what_adk_captured(otel, turn):
    capture = otel(environment="dev", exporter_content=False)  # ADK captures everything
    await turn()

    assert {"invoke_agent", "execute_tool"} <= {s.name.split(" ")[0] for s in capture.spans()}
    assert not any(s in everything(capture) for s in SENTINELS)


def test_lockdown_forces_the_three_adk_settings_over_operator_values():
    operator = {
        "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "true",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "SPAN_AND_EVENT",
        "ADK_TELEMETRY_IGNORE_RUN_CONFIG": "0",
    }
    assert policy.content_env(False, operator) == {
        "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "false",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "NO_CONTENT",
        "ADK_TELEMETRY_IGNORE_RUN_CONFIG": "1",
        "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
    }


def test_dev_turns_content_on_but_keeps_an_operators_choice():
    assert policy.content_env(True, {}) == {
        "ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "true",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "SPAN_AND_EVENT",
        "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
    }
    chosen = {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "EVENT_ONLY", "OTEL_SEMCONV_STABILITY_OPT_IN": "x"}
    assert policy.content_env(True, chosen) == {"ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS": "true"}


@pytest.mark.parametrize(
    ("value", "environment", "content"),
    [("dev", "dev", True), (" DEV ", "dev", True), ("ci", "ci", False), ("prod", "prod", False),
     ("", "unknown", False), ("staging", "unknown", False), ("development", "unknown", False)],
)
def test_only_dev_allows_content(monkeypatch, value, environment, content):
    monkeypatch.setenv("WCL_ENVIRONMENT", value)
    config = load_config()
    assert (config.environment, config.content_allowed) == (environment, content)
