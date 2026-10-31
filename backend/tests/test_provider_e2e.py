"""Sprint 2026-10-31 end-to-end check for epic 248 (feature 035): one switch moves every LLM call.

With ``WCL_LLM_PROVIDER=anthropic`` the chat agent, follow-up suggestions, chat titles, report
synthesis and the guide pipeline reach only the (faked) Anthropic API and never genai; with
``vertex`` they reach only Vertex (genai for the Gemini role defaults, Model Garden for a Claude
chat). Plus the grep check: outside the provider layer nothing builds or calls a model client.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from pydantic import BaseModel

from backend.app import suggestions
from backend.app.services import conversation_titles, report_synthesis
from backend.app.services.guide_pipeline import llm as guide_llm
from backend.tests.llm_fakes import gemini_reply, llm, message, text  # noqa: F401 - fixture
from backend.tests.test_llm_provider_agent import (  # noqa: F401
    ScriptedApi,
    _turn,
    scripted,
    text_answer,
)
from wcl_agent.llm.provider import ModelRole, role_model

ROOT = Path(__file__).resolve().parents[2]
CLAUDE_CHAT = "claude-sonnet-5-5"


class _Claim(BaseModel):
    text: str


async def _every_call() -> None:
    """Suggestions, a title, a findings report, a structured guide step and guide research."""
    assert await suggestions.generate_followups(None, "q", "a real answer") == ["Next?"]
    assert await conversation_titles.generate_title("q", "a") == "A title"
    assert await report_synthesis.synthesize_findings([{"role": "agent", "content": "x"}], scope="conversation")
    assert await guide_llm.generate_structured(role_model(ModelRole.GUIDE_REVIEW), "review", _Claim)
    grounded = await guide_llm.generate_grounded(role_model(ModelRole.GUIDE), "research", fetch_domains=[])
    assert grounded.text == "notes"


async def test_anthropic_reaches_only_the_anthropic_api(llm, scripted):
    llm.use("anthropic")
    api = llm.claude(
        message(text('["Next?"]')),
        message(text("A title")),
        message(text("## Summary")),
        message(text('{"text": "ok"}')),
        message(text("notes")),
    )
    genai = llm.genai()
    agent = scripted(ScriptedApi(text_answer("Hi.")))

    await _every_call()
    await _turn(CLAUDE_CHAT)

    assert api.hosts == ["api.anthropic.com"] * 5
    assert [b["model"] for b in api.bodies] == [
        "claude-haiku-5-5", "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-sonnet-5-5",
    ]
    assert [r.url.host for r in agent.requests] == ["api.anthropic.com"]
    assert genai.calls == []


async def test_vertex_reaches_only_vertex(llm, scripted):
    llm.use("vertex")
    api = llm.claude()
    genai = llm.genai(
        SimpleNamespace(text='["Next?"]'),
        SimpleNamespace(text="A title"),
        SimpleNamespace(text="## Summary"),
        SimpleNamespace(text='{"text": "ok"}'),
        gemini_reply("notes"),
    )
    agent = scripted(ScriptedApi(text_answer("Hi.")), access_token="fake-token")

    await _every_call()
    await _turn(CLAUDE_CHAT)

    assert [c.model for c in genai.calls] == [
        "gemini-3.6-flash", "gemini-3.6-flash", "gemini-3.6-flash", "gemini-3.1-pro-preview", "gemini-3.7-flash",
    ]
    assert api.bodies == []
    assert [r.url.host for r in agent.requests] == ["aiplatform.googleapis.com"]


# --- the grep check (plan "End-to-end acceptance") --------------------------------------

# Only these modules decide the provider or build/call model clients (ADK agent types and the
# google.genai `types` module are not clients and are allowed everywhere).
PROVIDER_LAYER = {"wcl_agent/llm/provider.py", "wcl_agent/llm/generation.py"}
# Read the provider without choosing a client for a model call (scrum master; 033 discovery).
READS_PROVIDER = {
    "backend/app/config.py",  # read-only Settings.llm_provider
    "backend/app/main.py",  # the sc-159 startup log line and the model-catalog cache key
    "backend/app/api/models.py",  # the sc-251 read-only `provider` field for the picker label
    "wcl_agent/llm/models.py",  # provider-specific discovery: id shape and which catalog to list
}
CLIENT_ALLOWED = {
    "wcl_agent/llm/model_retry.py": "ADK model wrappers take the provider's client; rate-limit classification",
    "wcl_agent/llm/models.py": "model discovery probes (033)",
}
CLIENT_USE = re.compile(
    r"from google import genai|import google\.genai\b|^\s*import anthropic\b|^\s*from anthropic\b"
    r"|genai_client\(|anthropic_client\(|\.generate_content\(|\.messages\.create\(",
    re.MULTILINE,
)


def _sources() -> list[tuple[str, str]]:
    files = sorted((ROOT / "backend" / "app").rglob("*.py")) + sorted((ROOT / "wcl_agent").rglob("*.py"))
    return [(str(p.relative_to(ROOT)), p.read_text(encoding="utf-8")) for p in files]


def test_only_the_provider_layer_calls_model_clients():
    offenders = [
        f"{path}: {m.group(0).strip()}"
        for path, source in _sources()
        if path not in PROVIDER_LAYER and path not in CLIENT_ALLOWED
        for m in CLIENT_USE.finditer(source)
    ]
    assert offenders == []


def test_only_the_provider_layer_reads_the_provider():
    offenders = [
        path
        for path, source in _sources()
        if "active_provider(" in source and path not in PROVIDER_LAYER | READS_PROVIDER
    ]
    assert offenders == []


def test_the_call_sites_import_no_provider_sdk_and_never_branch():
    # sc-252 AC 1 (and the guide pipeline's model module): no SDK types, no provider branch.
    for path in (
        "backend/app/suggestions.py",
        "backend/app/services/conversation_titles.py",
        "backend/app/services/report_synthesis.py",
        "backend/app/services/guide_pipeline/llm.py",
    ):
        source = (ROOT / path).read_text(encoding="utf-8")
        assert not re.search(r"google\.genai|^\s*(import|from) anthropic\b", source, re.MULTILINE), path
        assert "WCL_LLM_PROVIDER" not in source and "active_provider" not in source, path
