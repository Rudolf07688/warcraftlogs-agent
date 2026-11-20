"""Live pre-check for 080 (team-lead runs it; developers never call a real model).

Runs one chat-like turn through the app's ADK runner and reports, per model call, how the
`thought` parts arrive: counts, lengths and authors only, never their text. Usage (repo root,
with the app's env loaded):

    uv run python specs/080-thinking-status/livecheck_thoughts.py [MODEL]

MODEL defaults to the chat default (WCL_DEFAULT_MODEL).
"""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root

from google.genai import types  # noqa: E402

from backend.app import agent_runner  # noqa: E402
from backend.app.config import settings  # noqa: E402

QUESTION = (
    "Use your tools: find the last boss of the current raid tier and tell me which three "
    "DPS specs rank highest on it on Mythic. Keep the answer short."
)


async def main(model: str) -> None:
    runner = agent_runner._get_runner(model)
    session_id = f"livecheck-080-{uuid.uuid4().hex[:8]}"
    user_id = "livecheck-080"
    await agent_runner._ensure_session(session_id, user_id)
    message = types.Content(role="user", parts=[types.Part(text=QUESTION)])
    started = time.monotonic()
    calls = 0
    thought = Counter()
    lens: list[int] = []
    authors: Counter = Counter()
    order: list[str] = []
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=message,
        run_config=agent_runner._RUN_CONFIG,
    ):
        partial = bool(getattr(event, "partial", False))
        for part in (event.content.parts if event.content and event.content.parts else []):
            t = round(time.monotonic() - started, 1)
            if getattr(part, "thought", False):
                n = len(part.text or "")
                thought["partial" if partial else "final"] += 1
                if partial:
                    lens.append(n)
                authors[event.author] += 1
                kind = "thought"
            elif getattr(part, "function_call", None):
                kind = "call" if not partial else "call-partial"
                calls += 0 if partial else 1
            elif getattr(part, "function_response", None):
                kind = "result"
            elif getattr(part, "text", None):
                kind = "text" if partial else "text-final"
            else:
                continue
            if not order or order[-1].split("@")[0] != kind:
                order.append(f"{kind}@{t}s")
    print(f"model={model} tool_calls={calls} thought_parts={dict(thought)} authors={dict(authors)}")
    if lens:
        print(f"partial thought chunk chars: n={len(lens)} min={min(lens)} max={max(lens)} "
              f"sum={sum(lens)}")
    print("sequence (kind@first-seen):", " ".join(order))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else settings.default_model))
