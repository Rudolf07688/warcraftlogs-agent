"""The fixed part of a chat request stays within a token budget (064, sc-367).

The fixed part is what every model request of every chat turn carries before the user's data:
the system instruction (with the capability summary) and the tool schemas as the provider gets
them. The KNOWN PLAYER CONTEXT preamble comes on top and depends on the user. Tokens are
estimated as characters / 4, like the 046 and 050 size tests (Claude counts JSON denser, so the
live figure runs higher). At 0678ea7 the chat agent's fixed part was 14,396 (Claude) and 14,495
(Gemini); 064 cut it to the figures in ``MEASURED``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from google.adk.models.anthropic_llm import function_declaration_to_tool_param
from google.adk.models.llm_request import LlmRequest
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.function_tool import FunctionTool
from google.genai import types

from backend.app.agent_runner import _get_runner
from wcl_agent.agent import RAID_KICKOFF_OPENING, _untitled, build_instruction, drop_schema_titles

GEMINI = "gemini-2.5-flash"
CLAUDE = "claude-sonnet-4@20250514"
# Measured after the cuts (chars / 4); the budget leaves about 10% headroom for new tools and
# rules. Raise it only with a measurement table on the board: every token here is paid on every
# model request of every turn.
MEASURED = {GEMINI: 11_579, CLAUDE: 11_482}
FIXED_BUDGET = 12_733  # 12_800 less the 67 sc-514 saved (ProfileChangeIn docstring)
# The recent-raid kickoff turn adds only its playbook to the instruction.
KICKOFF_PLAYBOOK_BUDGET = 250


def _tokens(chars: int) -> int:
    return chars // 4


async def _request(model: str) -> tuple[object, LlmRequest]:
    """The chat agent and a model request carrying its tools, after the agent's callbacks."""
    agent = _get_runner(model).agent
    request = LlmRequest(model=model, config=types.GenerateContentConfig())
    request.append_tools(await agent.canonical_tools())
    for callback in agent.before_model_callback:
        assert callback(None, request) is None
    return agent, request


def _declarations(request: LlmRequest) -> list[types.FunctionDeclaration]:
    return [d for tool in request.config.tools for d in tool.function_declarations or []]


def _schema_chars(model: str, request: LlmRequest) -> int:
    """The tool schemas as the provider sends them (Anthropic: name, description, input_schema)."""
    if model.startswith("claude"):
        wire = [dict(function_declaration_to_tool_param(d)) for d in _declarations(request)]
    else:
        wire = [d.model_dump(exclude_none=True, mode="json") for d in _declarations(request)]
    return sum(len(json.dumps(tool)) for tool in wire)


@pytest.mark.parametrize("model", [GEMINI, CLAUDE])
async def test_the_fixed_part_of_a_chat_request_stays_within_budget(model):
    agent, request = await _request(model)
    instruction = _tokens(len(agent.instruction(None)))
    schemas = _tokens(_schema_chars(model, request))
    print(f"{model}: instruction {instruction} + tool schemas {schemas} = {instruction + schemas}")
    assert instruction + schemas <= FIXED_BUDGET


@pytest.mark.parametrize("model", [GEMINI, CLAUDE])
async def test_the_kickoff_turn_adds_only_its_playbook(model):
    agent = _get_runner(model).agent
    ctx = SimpleNamespace(user_content=types.Content(role="user", parts=[types.Part(text=RAID_KICKOFF_OPENING)]))
    kickoff = build_instruction(ctx, **agent.instruction.keywords)
    extra = _tokens(len(kickoff) - len(agent.instruction(None)))
    assert 0 < extra <= KICKOFF_PLAYBOOK_BUDGET


def _has_title_keyword(schema) -> bool:
    if isinstance(schema, list):
        return any(_has_title_keyword(item) for item in schema)
    if not isinstance(schema, dict):
        return False
    if isinstance(schema.get("title"), str):
        return True
    return any(
        _has_title_keyword(sub if key not in ("properties", "$defs") else list(sub.values()))
        for key, sub in schema.items()
    )


@pytest.mark.parametrize("model", [GEMINI, CLAUDE])
async def test_the_request_sends_every_tool_schema_without_titles_and_otherwise_unchanged(model):
    agent, request = await _request(model)
    sent = {d.name: d for d in _declarations(request)}
    tools = [t if isinstance(t, BaseTool) else FunctionTool(t) for t in agent.tools]
    assert set(sent) == {t.name for t in tools}
    for tool in tools:
        original = tool._get_declaration()
        assert sent[tool.name].description == original.description
        schema = sent[tool.name].parameters_json_schema
        if original.parameters_json_schema is None:
            assert schema is None
            continue
        assert schema == _untitled(original.parameters_json_schema)
        assert not _has_title_keyword(schema)
        assert schema.get("required") == original.parameters_json_schema.get("required")
        assert list(schema.get("properties", {})) == list(original.parameters_json_schema.get("properties", {}))


def test_untitled_keeps_a_parameter_named_title_and_every_other_keyword():
    schema = {
        "title": "create_chartParams",
        "type": "object",
        "properties": {
            "title": {"title": "Title", "type": "string"},
            "kind": {"anyOf": [{"enum": ["line", "bar"], "type": "string", "title": "K"}, {"type": "null"}],
                     "default": None, "title": "Kind"},
            "rows": {"type": "array", "items": {"$ref": "#/$defs/Row"}, "title": "Rows"},
        },
        "$defs": {"Row": {"title": "Row", "description": "One row.", "type": "object",
                          "properties": {"title": {"type": "string", "default": "Title"}}}},
        "required": ["title"],
    }
    assert _untitled(schema) == {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "kind": {"anyOf": [{"enum": ["line", "bar"], "type": "string"}, {"type": "null"}], "default": None},
            "rows": {"type": "array", "items": {"$ref": "#/$defs/Row"}},
        },
        "$defs": {"Row": {"description": "One row.", "type": "object",
                          "properties": {"title": {"type": "string", "default": "Title"}}}},
        "required": ["title"],
    }


def test_the_callback_leaves_a_request_without_tools_alone():
    request = LlmRequest(model=GEMINI, config=types.GenerateContentConfig())
    assert drop_schema_titles(None, request) is None
    assert request.config.tools is None
