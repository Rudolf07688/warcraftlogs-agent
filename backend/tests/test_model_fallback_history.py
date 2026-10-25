"""Feature 021 / SC-007: after a sibling switch the ADK history holds the turn exactly once.

A real ADK ``Runner`` over an ``InMemorySessionService`` runs a real ``RetryingGemini``
whose genai client is fake: the first model request (on A) asks for a tool, the second is
rate limited on A and answered by the sibling B. The turn goes through
``agent_runner.stream_response`` like a chat turn. No Vertex needed.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from backend.app import agent_runner
from backend.tests.test_model_fallback import A, B, POLICY, FakeGenai, _gemini, _text_response
from wcl_agent.llm.model_retry import make_before_model_callback

ANSWER = "Three fights, two wipes."


def _call_response() -> types.GenerateContentResponse:
    call = types.FunctionCall(name="lookup_report", args={"report_code": "abc"})
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(function_call=call)]),
                finish_reason="STOP",
            )
        ]
    )


async def test_switch_mid_turn_keeps_the_history_exactly_once(monkeypatch):
    lookups: list[str] = []

    async def lookup_report(report_code: str) -> dict:
        """Look up a Warcraft Logs report."""
        lookups.append(report_code)
        return {"status": "success", "fights": 3}

    client = FakeGenai()

    def respond(model: str, n: int):
        if n == 1:
            client.busy = {A}  # A runs out of quota after the tool request
            return _call_response()
        return _text_response(ANSWER)

    client.respond = respond
    agent = Agent(
        name="wcl_agent",
        model=_gemini(A, client),
        instruction="Answer from the report.",
        tools=[lookup_report],
        before_model_callback=make_before_model_callback(POLICY),
    )
    service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=agent_runner.APP_NAME, session_service=service)
    monkeypatch.setattr(agent_runner, "_get_runner", lambda model: runner)
    monkeypatch.setattr(agent_runner, "_session_service", service)

    records = [
        r
        async for r in agent_runner.stream_response(A, "s1", "How did we do?", fallback_model=B)
    ]

    assert client.calls == [A, A, A, B]  # tool round on A, 2 rate-limited tries, B answers
    assert lookups == ["abc"]  # the tool ran once
    assert [r for r in records if r["type"] == "model_fallback"] == [
        {"type": "model_fallback", "from_model": A, "to_model": B}
    ]
    tokens = "".join(r["text"] for r in records if r["type"] == "token")
    assert tokens == ANSWER

    session = await service.get_session(
        app_name=agent_runner.APP_NAME, user_id=agent_runner.USER_ID, session_id="s1"
    )
    parts = [(e.author, p) for e in session.events for p in (e.content.parts if e.content else [])]
    user_texts = [p.text for author, p in parts if author == "user" and p.text]
    calls = [p.function_call.name for _, p in parts if p.function_call]
    results = [p.function_response.name for _, p in parts if p.function_response]
    answers = [p.text for author, p in parts if author == "wcl_agent" and p.text and not p.thought]
    assert user_texts == ["How did we do?"]
    assert calls == ["lookup_report"]
    assert results == ["lookup_report"]
    assert answers == [ANSWER]
