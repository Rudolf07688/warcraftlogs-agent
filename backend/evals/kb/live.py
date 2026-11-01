"""Team-lead's live modes for the knowledge search eval (feature 044, sc-115 AC2-AC3).

``record`` embeds the fixture corpus (``RETRIEVAL_DOCUMENT``) and the questions
(``RETRIEVAL_QUERY``) with the real embedder and writes ``embeddings.json``, so CI's recall
numbers mean something. ``live`` asks each labelled question as one agent turn on a cheap chat
model, once with the search-first clause and once without it, and reports how accurately the
agent fills the search filters and how many turns it answered without a Warcraft Logs call.
Both call live services: never from pytest.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from .harness import EMBEDDINGS, REAL_PREFIX, load_corpus, load_embeddings, load_questions, seed

SEARCH_FIRST_START = "Local first:"
SEARCH_FIRST_END = "Plan the evidence"


async def record(*, max_texts: int = 300) -> int:
    from backend.app.kb.embedder import get_embedder

    embedder = get_embedder()
    if embedder is None:
        print("No embedder is configured (get_embedder() is None); nothing recorded.")
        return 2
    corpus, questions = load_corpus(), load_questions()
    chunks = [c for kind in corpus.values() for c in kind]
    if len(chunks) + len(questions) > max_texts:
        print(f"{len(chunks) + len(questions)} texts exceed --max-texts {max_texts}; nothing recorded.")
        return 2
    vectors: dict[str, list[float]] = {}
    documents = await embedder.embed([c["text"] for c in chunks], task="RETRIEVAL_DOCUMENT")
    vectors.update({c["id"]: v for c, v in zip(chunks, documents, strict=True)})
    queries = await embedder.embed([q["question"] for q in questions], task="RETRIEVAL_QUERY")
    vectors.update({q["id"]: v for q, v in zip(questions, queries, strict=True)})
    rounded = {key: [round(x, 6) for x in vector] for key, vector in vectors.items()}
    EMBEDDINGS.write_text(json.dumps({"set": f"{REAL_PREFIX}{embedder.model}", "dim": len(documents[0]), "vectors": rounded}))
    print(f"Recorded {len(rounded)} vectors with {embedder.model} to {EMBEDDINGS}.")
    return 0


def strip_search_first(instruction: str) -> str:
    """The instruction without the search-first clause (the 'without' variant)."""
    start, end = instruction.find(SEARCH_FIRST_START), instruction.find(SEARCH_FIRST_END)
    return instruction[:start] + instruction[end:] if 0 <= start < end else instruction


def filter_matches(args: dict[str, Any], expected: dict[str, Any]) -> tuple[int, int]:
    """(labelled filters the agent got right, labelled filters) for one search call."""
    from backend.app.services.name_resolver import ResolutionError, name_key, resolve_class

    def same(key: str, got: Any, want: Any) -> bool:
        if got is None:
            return False
        if key == "class_name":
            try:
                return resolve_class(str(got)) == resolve_class(str(want))
            except ResolutionError:
                return False
        if key in ("encounter", "character", "spec"):
            return name_key(str(got)) == name_key(str(want))
        return str(got) == str(want)

    right = sum(same(key, args.get(key), want) for key, want in expected.items())
    return right, len(expected)


async def live(maker, *, max_questions: int = 30, model: str | None = None) -> int:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools.function_tool import FunctionTool
    from google.genai import types

    from backend.app.agent_tools.kb_tools import KB_TOOLS
    from backend.app.agent_tools.profile_tools import PROFILE_TOOLS
    from backend.app.agent_tools.stored_data_tools import STORED_DATA_TOOLS
    from backend.app.tenancy.context import RequestIdentity, current_identity
    from wcl_agent.agent import TOOL_GROUPS, build_agent
    from wcl_agent.llm.provider import ModelRole, role_model

    model = model or role_model(ModelRole.FAST)
    _, vectors = load_embeddings()
    tenant_id, _ = await seed(maker, vectors)
    wcl_tools = {FunctionTool(t).name for group in TOOL_GROUPS for t in group.tools}
    questions = load_questions()[:max_questions]
    token = current_identity.set(RequestIdentity(uuid.uuid4(), tenant_id, "owner", False, uuid.uuid4()))
    report: dict[str, Any] = {"model": model, "questions": len(questions), "variants": {}}
    try:
        for variant in ("search_first", "without"):
            agent = build_agent(model, extra_groups=(PROFILE_TOOLS, KB_TOOLS, STORED_DATA_TOOLS))
            if variant == "without":
                original = agent.instruction
                agent.instruction = lambda ctx, _original=original: strip_search_first(_original(ctx))
            runner = Runner(agent=agent, app_name="kb_eval", session_service=InMemorySessionService())
            local = searched = right = labelled = 0
            for q in questions:
                session = await runner.session_service.create_session(app_name="kb_eval", user_id=str(tenant_id))
                calls: list[tuple[str, dict]] = []
                message = types.Content(role="user", parts=[types.Part(text=q["question"])])
                async for event in runner.run_async(user_id=str(tenant_id), session_id=session.id, new_message=message):
                    for part in (event.content.parts if event.content and event.content.parts else []):
                        call = getattr(part, "function_call", None)
                        if call and not getattr(event, "partial", False):
                            calls.append((call.name, dict(call.args or {})))
                local += not any(name in wcl_tools for name, _ in calls)
                first = next((args for name, args in calls if name == "search_knowledge"), None)
                if first is not None:
                    searched += 1
                    got, total = filter_matches(first, q["filters"])
                    right, labelled = right + got, labelled + total
            report["variants"][variant] = {
                "local_answer_rate": round(local / len(questions), 3),
                "search_rate": round(searched / len(questions), 3),
                "filter_accuracy": round(right / labelled, 3) if labelled else None,
            }
    finally:
        current_identity.reset(token)
    print(json.dumps(report, indent=1))
    return 0
