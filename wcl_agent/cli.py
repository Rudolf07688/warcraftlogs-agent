"""Interactive Warcraft Logs analysis chat (console entry point ``wcl``).

Flow: load credentials -> pick a raid encounter + difficulty from a live menu ->
drop into a chat REPL backed by a Google ADK agent (Gemini) that pulls and
analyzes ranking data for the selected fight.
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

APP_NAME = "wcl_app"
USER_ID = "local_user"
SESSION_ID = "session_main"


def _check_env() -> None:
    required = ["WCL_CLIENT_ID", "WCL_CLIENT_SECRET"]
    # Gemini auth: Vertex AI (ADC) by default, or an AI Studio API key.
    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE":
        required.append("GOOGLE_CLOUD_PROJECT")
    else:
        required.append("GOOGLE_API_KEY")

    missing = [var for var in required if not os.getenv(var)]
    if missing:
        print("Missing required environment variables: " + ", ".join(missing))
        print("Copy .env.example to .env and fill it in, then re-run.")
        if "GOOGLE_CLOUD_PROJECT" in missing:
            print("For Vertex AI also run: gcloud auth application-default login")
        sys.exit(1)


async def _call_agent(runner, query: str) -> None:
    """Send one user turn to the agent and print tool calls + final answer."""
    from google.genai import types

    content = types.Content(role="user", parts=[types.Part(text=query)])
    final = "(no response)"
    async for event in runner.run_async(
        user_id=USER_ID, session_id=SESSION_ID, new_message=content
    ):
        # Surface tool activity so the user can see the agent working.
        if event.content and event.content.parts:
            for part in event.content.parts:
                call = getattr(part, "function_call", None)
                if call:
                    print(f"  [calling {call.name}...]")
        if event.is_final_response():
            if event.content and event.content.parts and event.content.parts[0].text:
                final = event.content.parts[0].text
            elif event.actions and getattr(event.actions, "escalate", False):
                final = f"Agent escalated: {event.error_message or 'no message'}"
    print(f"\nAgent: {final}")


async def _main() -> None:
    load_dotenv()
    _check_env()

    # Imported after env is loaded so ADK/WCL pick up credentials.
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    from wcl_agent.agent import root_agent
    from wcl_agent.menu import select_encounter

    context = select_encounter()

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID, state=context
    )
    runner = Runner(
        agent=root_agent, app_name=APP_NAME, session_service=session_service
    )

    print(
        f"Chatting about {context['encounterName']} ({context['difficultyName']}). "
        "Ask e.g. 'How well are hunters performing?'. Type 'exit' to quit."
    )
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break
        await _call_agent(runner, user_input)


def run() -> None:
    """Synchronous entry point for the ``wcl`` console script."""
    asyncio.run(_main())


if __name__ == "__main__":
    run()
