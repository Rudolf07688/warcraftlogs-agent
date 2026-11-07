#!/usr/bin/env python3
"""Offline size of a chat request, per part and provider: chars and estimated tokens.

Agent-facing. Builds the chat agent the way the app does (backend.app.agent_runner._get_runner),
applies its before-model callbacks to a request carrying its tools, and measures what the
provider gets, as backend/tests/test_064_prompt_budget.py does:

  instruction     the system instruction (with the capability summary)
  tool schemas    the tool declarations in the provider's wire form (Anthropic: name,
                  description, input_schema; Gemini: the FunctionDeclaration JSON)
  history         --history FILE: a JSON list of {"role": "user"|"model", "text": "..."}
  message         --message TEXT: the new user turn

Tokens are an ESTIMATE, chars / --chars-per-token (default 4, as the 046/050/064 size tests).
No exact tokenizer runs offline here without a new dependency or a network call (Anthropic's
and Vertex's count_tokens are API calls), and Claude counts JSON denser, so its live figure
runs higher. The per-user KNOWN PLAYER CONTEXT preamble is not included.

  tokens.py [--model M ...] [--history FILE] [--message TEXT] [--json] [--chars-per-token N]

Runs under `uv run` in a cleared environment (HOME and PATH only, WCL_LOAD_DOTENV=0), so no
.env, shell setting or credential reaches it, and it makes no network call.
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GEMINI = "gemini-2.5-flash"
CLAUDE = "claude-sonnet-4@20250514"
INNER = "WCL_TOKENS_INNER"
HISTORY = "WCL_TOKENS_HISTORY"   # the caller's --history file as an absolute path, set by the wrapper


def _contents(history, message):
    from google.genai import types

    turns = list(history) + ([{"role": "user", "text": message}] if message else [])
    return [types.Content(role=t["role"], parts=[types.Part(text=t["text"])]) for t in turns]


def _wire_chars(model, contents):
    if model.startswith("claude"):
        from google.adk.models.anthropic_llm import content_to_message_param

        return sum(len(json.dumps(content_to_message_param(c), default=str)) for c in contents)
    return sum(len(json.dumps(c.model_dump(exclude_none=True, mode="json"))) for c in contents)


async def measure(model, history=(), message=None):
    """{part: chars} for one chat request to MODEL, as the provider receives it."""
    from google.adk.models.anthropic_llm import function_declaration_to_tool_param
    from google.adk.models.llm_request import LlmRequest
    from google.genai import types

    from backend.app.agent_runner import _get_runner

    agent = _get_runner(model).agent
    request = LlmRequest(model=model, config=types.GenerateContentConfig())
    request.append_tools(await agent.canonical_tools())
    for callback in agent.before_model_callback:
        callback(None, request)
    decls = [d for tool in request.config.tools for d in tool.function_declarations or []]
    if model.startswith("claude"):
        wire = [dict(function_declaration_to_tool_param(d)) for d in decls]
    else:
        wire = [d.model_dump(exclude_none=True, mode="json") for d in decls]
    return {
        "instruction": len(agent.instruction(None)),
        "tool schemas": sum(len(json.dumps(tool)) for tool in wire),
        "history": _wire_chars(model, _contents(history, None)),
        "message": _wire_chars(model, _contents((), message)),
    }


def report(results, per_token):
    label = f"~tokens (chars/{per_token:g}, estimate)"
    lines = [f"{'model':<28} {'part':<13} {'chars':>8} {label:>30}"]
    for model, parts in results.items():
        for part, chars in {**parts, "total": sum(parts.values())}.items():
            lines.append(f"{model:<28} {part:<13} {chars:>8} {round(chars / per_token):>30}")
    return "\n".join(lines)


def inner(a):
    path = os.environ.get(HISTORY) or a.history
    history = json.loads(Path(path).read_text()) if path else []
    results = {m: asyncio.run(measure(m, history, a.message)) for m in a.model or [GEMINI, CLAUDE]}
    if a.json:
        print(json.dumps({"estimate": f"chars/{a.chars_per_token:g}", "models": {
            m: {p: {"chars": c, "tokens": round(c / a.chars_per_token)} for p, c in parts.items()}
            for m, parts in results.items()}}, indent=2))
    else:
        print(report(results, a.chars_per_token))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", action="append", help=f"repeatable; default {GEMINI} and {CLAUDE}")
    p.add_argument("--history", help='JSON list of {"role": "user"|"model", "text": "..."}')
    p.add_argument("--message", help="the new user turn")
    p.add_argument("--json", action="store_true")
    p.add_argument("--chars-per-token", type=float, default=4.0)
    a = p.parse_args(argv)
    if os.environ.get(INNER) == "1":
        return inner(a)
    args = list(sys.argv[1:] if argv is None else argv)
    env = {"HOME": os.environ["HOME"], "PATH": os.environ["PATH"], "WCL_LOAD_DOTENV": "0", INNER: "1"}
    if a.history:  # the inner run starts in the repo root, so it gets the path from here (any spelling)
        env[HISTORY] = str(Path(a.history).resolve())
    cmd = ["uv", "run", "--quiet", "--project", str(REPO), "python", "-W", "ignore::UserWarning", str(Path(__file__).resolve()), *args]
    return subprocess.run(cmd, cwd=REPO, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
