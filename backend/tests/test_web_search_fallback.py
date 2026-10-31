"""sc-184: the web_search sub-agent after a model fallback.

A real ADK ``Runner`` runs the root model and the real ``web_search`` sub-agent tool over
one fake genai client, as in ``test_model_fallback_history``. The turn goes through
``agent_runner.stream_response`` like a chat turn. No Vertex needed.
"""

from __future__ import annotations

import pytest
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import errors as genai_errors
from google.genai import types

from backend.app import agent_runner
from backend.tests.test_model_fallback import A, B, POLICY, FakeGenai, _gemini, _text_response
from wcl_agent.agent import WEB_SEARCH_AGENT_NAME, _build_web_search_tool
from wcl_agent.llm.model_retry import ModelRateLimited, make_before_model_callback

ANSWER = "The tuning lands next week."
SEARCHED = "Hotfix notes say next week."


def _search_call() -> types.GenerateContentResponse:
    call = types.FunctionCall(name=WEB_SEARCH_AGENT_NAME, args={"request": "class tuning hotfix"})
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(function_call=call)]),
                finish_reason="STOP",
            )
        ]
    )


def _is_search_request(contents) -> bool:
    """The sub-agent's own request: its first user message is the search request."""
    first = contents[0].parts[0].text if contents and contents[0].parts else ""
    return "class tuning hotfix" in (first or "")


async def _turn(monkeypatch, client: FakeGenai) -> list[dict]:
    web_search = _build_web_search_tool(A, POLICY)
    web_search.agent.model.client = client
    agent = Agent(
        name="wcl_agent",
        model=_gemini(A, client),
        instruction="Answer the question.",
        tools=[web_search],
        before_model_callback=make_before_model_callback(POLICY),
    )
    service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=agent_runner.APP_NAME, session_service=service)
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: runner)
    monkeypatch.setattr(agent_runner, "_session_service", service)
    return [
        r
        async for r in agent_runner.stream_response(A, "s1", "When is the tuning?", fallback_model=B)
    ]


def _respond(model: str, contents) -> types.GenerateContentResponse:
    if _is_search_request(contents):
        return _text_response(SEARCHED)
    if any(p.function_response for c in contents for p in (c.parts or [])):
        return _text_response(ANSWER)
    return _search_call()


async def test_web_search_after_a_switch_follows_the_sibling(monkeypatch):
    # A is busy from the start: the turn switches to B, B asks for a web search.
    client = FakeGenai(busy={A})
    client.respond = lambda model, n: _respond(model, client.contents[-1])
    records = await _turn(monkeypatch, client)
    assert client.calls == [A, A, B, B, B]  # 2 tries on A, B asks, search on B, B answers
    assert "".join(r["text"] for r in records if r["type"] == "token") == ANSWER
    assert [r["type"] for r in records].count("model_fallback") == 1


async def test_web_search_rate_limit_never_reaches_the_user_raw(monkeypatch):
    # Both busy for the search only: the root answers without it, from the tool error.
    client = FakeGenai()
    searches: list[str] = []

    def respond(model, n):
        contents = client.contents[-1]
        if _is_search_request(contents):
            searches.append(model)
            raise genai_errors.ClientError(
                429, {"error": {"code": 429, "message": "Resource exhausted. RAW-PROVIDER-TEXT",
                                "status": "RESOURCE_EXHAUSTED"}}
            )
        return _respond(model, contents)

    client.respond = respond
    records = await _turn(monkeypatch, client)
    assert searches == [A, A]  # the search got the retry policy, then gave up
    assert "".join(r["text"] for r in records if r["type"] == "token") == ANSWER
    assert "RAW-PROVIDER-TEXT" not in repr(records)


async def test_other_web_search_errors_are_a_clean_tool_error(monkeypatch):
    client = FakeGenai()
    seen: list[str] = []

    def respond(model, n):
        contents = client.contents[-1]
        if _is_search_request(contents):
            raise genai_errors.ServerError(500, {"error": {"code": 500, "message": "RAW-PROVIDER-TEXT"}})
        for c in contents:
            for p in c.parts or []:
                if p.function_response:
                    seen.append(str(p.function_response.response))
        return _respond(model, contents)

    client.respond = respond
    records = await _turn(monkeypatch, client)
    assert "".join(r["text"] for r in records if r["type"] == "token") == ANSWER
    assert seen and all("RAW-PROVIDER-TEXT" not in s for s in seen)
    assert "Web search is unavailable" in seen[0]


async def test_a_root_model_rate_limit_still_propagates(monkeypatch):
    client = FakeGenai(busy={A, B})
    with pytest.raises(ModelRateLimited):
        await _turn(monkeypatch, client)
