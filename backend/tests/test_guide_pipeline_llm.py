"""Guide pipeline model calls on both providers (feature 035 / sc-253): faked clients only.

Structured output keeps one validation contract and one retry on either provider; research is
grounded by Google Search on Gemini and by Anthropic's web search (plus web fetch limited to the
fetch rules) on Claude.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.services.guide_pipeline import llm, research
from backend.app.services.guide_pipeline.models import GenerationBriefing
from backend.tests.llm_fakes import (  # noqa: F401 - fixtures
    fetch_result,
    gemini_reply,
    message,
    no_sleep,
    search_error,
    search_results,
    server_tool_use,
    text,
    web_search_not_enabled,
)
from backend.tests.llm_fakes import (
    llm as llm_fakes,
)
from wcl_agent.llm.provider import ModelRole, role_model

SONNET = "claude-sonnet-5-5"
GEMINI = "gemini-3.7-flash"


class Draft(BaseModel):
    title: str
    points: list[int]


@pytest.fixture
def fakes(llm_fakes):
    return llm_fakes


# --- structured output ------------------------------------------------------------------


async def test_claude_structured_output_asks_for_the_schema_and_validates(fakes):
    fakes.use("anthropic")
    api = fakes.claude(message(text('{"title": "Fire", "points": [1, 2]}'), model=SONNET))
    out = await llm.generate_structured(SONNET, "write", Draft)
    assert out == Draft(title="Fire", points=[1, 2])
    [body] = api.bodies
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert set(fmt["schema"]["properties"]) == {"title", "points"}
    assert fmt["schema"]["additionalProperties"] is False
    assert "temperature" not in body and "tool_choice" not in body and "tools" not in body


@pytest.mark.parametrize("provider_name", ["anthropic", "vertex"])
async def test_a_misfit_reply_is_retried_once(fakes, provider_name):
    fakes.use(provider_name)
    misfit, valid = '{"title": "Fire"}', '{"title": "Fire", "points": []}'
    if provider_name == "anthropic":
        calls = fakes.claude(message(text(misfit)), message(text(valid))).bodies
        model = SONNET
    else:
        calls = fakes.genai(SimpleNamespace(text=misfit), SimpleNamespace(text=valid)).calls
        model = GEMINI
    assert await llm.generate_structured(model, "write", Draft) == Draft(title="Fire", points=[])
    assert len(calls) == 2


@pytest.mark.parametrize("provider_name", ["anthropic", "vertex"])
async def test_two_misfits_raise_the_pipeline_error(fakes, provider_name):
    fakes.use(provider_name)
    if provider_name == "anthropic":
        fakes.claude(message(text("not json")), message(text("{}")))
        model = SONNET
    else:
        fakes.genai(SimpleNamespace(text="not json"), SimpleNamespace(text="{}"))
        model = GEMINI
    with pytest.raises(llm.GuideModelError, match="invalid structured output"):
        await llm.generate_structured(model, "write", Draft)


async def test_a_claude_api_error_is_a_pipeline_error(fakes):
    fakes.use("anthropic")
    fakes.claude((500, {"type": "error", "error": {"type": "api_error", "message": "boom"}}))
    with pytest.raises(llm.GuideModelError, match="InternalServerError"):
        await llm.generate_structured(SONNET, "write", Draft)


async def test_vertex_structured_request_config_is_unchanged(fakes):
    # CRITICAL-impact mitigation (generate_structured feeds 5 guide processes): the Gemini
    # request is exactly the pre-035 one.
    fakes.use("vertex")
    genai = fakes.genai(SimpleNamespace(text='{"title": "Fire", "points": [3]}'))
    await llm.generate_structured(GEMINI, "write", Draft, temperature=0.0)
    [call] = genai.calls
    assert (call.model, call.contents) == (GEMINI, "write")
    config = call.config
    assert config.response_mime_type == "application/json"
    assert config.response_schema is Draft
    assert config.temperature == 0.0
    assert config.tools is None and config.thinking_config is None and config.max_output_tokens is None


def test_anthropic_author_and_reviewer_default_to_different_models(fakes):
    fakes.use("anthropic")
    assert role_model(ModelRole.GUIDE) == "claude-sonnet-5-5"
    assert role_model(ModelRole.GUIDE_REVIEW) == "claude-opus-5-5"


# --- grounded research on Claude --------------------------------------------------------


async def test_claude_research_returns_text_and_deduplicated_sources(fakes):
    fakes.use("anthropic")
    api = fakes.claude(
        message(
            text("Searching. "),
            server_tool_use(),
            search_results(("Icy Veins", "https://www.icy-veins.com/fire"), ("Archon", "https://www.archon.gg/fire")),
            server_tool_use("web_fetch", "srvtoolu_2"),
            fetch_result("https://www.icy-veins.com/fire", "Icy Veins (fetched)"),
            fetch_result("https://worldofwarcraft.blizzard.com/news/1", "Hotfixes"),
            text("Fire uses Combustion."),
            model=SONNET,
        )
    )
    grounded = await llm.generate_grounded(SONNET, "research", fetch_domains=["worldofwarcraft.blizzard.com"])
    assert grounded.text == "Searching. Fire uses Combustion."
    assert grounded.sources == [
        {"title": "Icy Veins", "uri": "https://www.icy-veins.com/fire"},
        {"title": "Archon", "uri": "https://www.archon.gg/fire"},
        {"title": "Hotfixes", "uri": "https://worldofwarcraft.blizzard.com/news/1"},
    ]
    [body] = api.bodies
    assert body["tools"] == [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 10},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 5, "allowed_domains": ["worldofwarcraft.blizzard.com"]},
    ]
    assert "temperature" not in body and "tool_choice" not in body


async def test_a_paused_turn_is_resumed_with_the_paused_content(fakes):
    fakes.use("anthropic")
    first = message(server_tool_use(), search_results(("A", "https://a.example/1")), stop_reason="pause_turn", model=SONNET)
    api = fakes.claude(first, message(text("Done."), model=SONNET))
    grounded = await llm.generate_grounded(SONNET, "research", fetch_domains=[])
    assert grounded.text == "Done."
    assert grounded.sources == [{"title": "A", "uri": "https://a.example/1"}]
    resumed = api.bodies[1]["messages"]
    assert [m["role"] for m in resumed] == ["user", "assistant"]
    assert [b["type"] for b in resumed[1]["content"]] == ["server_tool_use", "web_search_tool_result"]
    assert resumed[1]["content"][1]["content"][0]["encrypted_content"] == "enc"  # sent back unchanged


async def test_resumes_are_bounded(fakes):
    fakes.use("anthropic")
    paused = message(text("x"), stop_reason="pause_turn", model=SONNET)
    api = fakes.claude(paused, paused, paused, paused)
    await llm.generate_grounded(SONNET, "research", fetch_domains=[])
    assert len(api.bodies) == 4  # the first call plus 3 resumes


async def test_no_fetch_domains_means_no_web_fetch_tool(fakes):
    fakes.use("anthropic")
    api = fakes.claude(message(text("notes"), model=SONNET))
    await llm.generate_grounded(SONNET, "research", fetch_domains=[])
    assert [t["name"] for t in api.bodies[0]["tools"]] == ["web_search"]


async def test_claude_on_vertex_gets_basic_search_and_no_fetch(fakes):
    fakes.use("vertex")
    api = fakes.claude(message(text("notes"), model=SONNET))
    await llm.generate_grounded(SONNET, "research", fetch_domains=["worldofwarcraft.blizzard.com"])
    assert api.bodies[0]["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}]


async def test_web_search_not_enabled_is_a_clear_pipeline_error(fakes):
    fakes.use("anthropic")
    fakes.claude(web_search_not_enabled())
    with pytest.raises(llm.GuideModelError) as err:
        await llm.generate_grounded(SONNET, "research", fetch_domains=[])
    assert "ServerToolDisabled" in str(err.value)
    assert "https://platform.claude.com/settings/capabilities" in str(err.value)


async def test_only_failed_searches_hold_the_run(fakes):
    # Clarify Q4: at least one search error and no results at all.
    fakes.use("anthropic")
    fakes.claude(message(server_tool_use(), search_error("too_many_requests"), text("I could not search."), model=SONNET))
    with pytest.raises(llm.GuideModelError, match="web search failed: too_many_requests"):
        await llm.generate_grounded(SONNET, "research", fetch_domains=[])


@pytest.mark.parametrize(
    "blocks",
    [
        (text("From memory."),),  # no searches at all
        (server_tool_use(), search_results(), text("Nothing new.")),  # a successful, empty search
    ],
)
async def test_unsearched_or_empty_research_continues(fakes, blocks):
    fakes.use("anthropic")
    fakes.claude(message(*blocks, model=SONNET))
    grounded = await llm.generate_grounded(SONNET, "research", fetch_domains=[])
    assert grounded.sources == [] and grounded.text


async def test_one_failed_search_among_results_continues(fakes):
    fakes.use("anthropic")
    fakes.claude(
        message(search_error("unavailable"), search_results(("B", "https://b.example")), text("ok"), model=SONNET)
    )
    grounded = await llm.generate_grounded(SONNET, "research", fetch_domains=[])
    assert grounded.sources == [{"title": "B", "uri": "https://b.example"}]


async def test_empty_claude_text_is_a_pipeline_error(fakes):
    fakes.use("anthropic")
    fakes.claude(message(server_tool_use(), search_results(("B", "https://b.example")), model=SONNET))
    with pytest.raises(llm.GuideModelError, match="no text"):
        await llm.generate_grounded(SONNET, "research", fetch_domains=[])


# --- grounded research on Gemini (unchanged) --------------------------------------------


async def test_gemini_research_request_and_sources_are_unchanged(fakes):
    fakes.use("vertex")
    genai = fakes.genai(gemini_reply(" notes ", (("icy-veins.com", "https://r/1"), ("icy-veins.com", "https://r/1"))))
    grounded = await llm.generate_grounded(GEMINI, "research", fetch_domains=["worldofwarcraft.blizzard.com"])
    assert grounded == llm.GroundedText("notes", [{"title": "icy-veins.com", "uri": "https://r/1"}])
    config = genai.calls[0].config
    assert config.temperature == 0.2
    assert [bool(t.google_search) for t in config.tools] == [True, False]
    assert config.tools[1].url_context is not None
    assert config.automatic_function_calling.disable is True


async def test_gemini_without_fetch_domains_has_no_url_context(fakes):
    fakes.use("vertex")
    genai = fakes.genai(gemini_reply("notes"))
    await llm.generate_grounded(GEMINI, "research", fetch_domains=[])
    assert len(genai.calls[0].config.tools) == 1


# --- the fetch rules reach the request (WCL_GUIDE_RESEARCH_FETCH_ENABLED) -----------------


BRIEFING = GenerationBriefing(
    now_utc=datetime(2026, 10, 31, tzinfo=UTC), content_type="raid", class_name="Mage",
    class_display="Mage", spec="Fire", role="dps", class_specs=["Arcane", "Fire", "Frost"],
    live_patch="12.1.5",
)


@pytest.mark.parametrize("enabled", [False, True])
async def test_research_fetches_only_the_allowed_domains(fakes, monkeypatch, enabled):
    fakes.use("anthropic")
    monkeypatch.setattr(settings, "wcl_guide_model", SONNET)
    monkeypatch.setattr(settings, "wcl_guide_research_fetch_enabled", enabled)
    api = fakes.claude(message(text("notes"), model=SONNET))

    async def no_extraction(model, prompt, schema, *, temperature=0.2):
        return schema()

    monkeypatch.setattr(llm, "generate_structured", no_extraction)
    await research.collect_evidence_basic(BRIEFING)
    [fetch] = [t for t in api.bodies[0]["tools"] if t["name"] == "web_fetch"]
    assert fetch["allowed_domains"] == research.fetchable_domains()
    official = {"worldofwarcraft.blizzard.com", "news.blizzard.com"}
    assert official <= set(fetch["allowed_domains"])
    assert ("icy-veins.com" in fetch["allowed_domains"]) is enabled
    assert "wowhead.com" not in fetch["allowed_domains"]  # never fetched (robots.txt)
