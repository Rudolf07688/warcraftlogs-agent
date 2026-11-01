"""Search-first prompting (feature 044, sc-115 AC1): the rendered instruction and capabilities."""

from __future__ import annotations

from backend.app.agent_runner import _get_runner
from backend.app.agent_tools.kb_tools import KB_TOOLS
from backend.app.agent_tools.profile_tools import PROFILE_TOOLS
from wcl_agent.agent import build_agent

LOOKUPS = ("list_stored_fights", "get_stored_fight_table", "list_stored_reports_for_character")


def _instruction(agent) -> str:
    return agent.instruction(None)


def test_rendered_instruction_puts_local_lookups_before_warcraft_logs():
    text = _instruction(build_agent("gemini-2.5-flash", extra_groups=(PROFILE_TOOLS, KB_TOOLS)))
    plan = text.split("<EVIDENCE_PLAN>", 1)[1].split("</EVIDENCE_PLAN>", 1)[0]
    clause = plan.split("Plan the evidence", 1)[0]
    assert "search_knowledge" in clause and all(name in clause for name in LOOKUPS)
    assert "before any\nWarcraft Logs fetch" in clause
    assert "exposed in this session" in clause  # the CLI agent has none of these tools


def test_capabilities_list_the_search_tool():
    text = _instruction(build_agent("gemini-2.5-flash", extra_groups=(PROFILE_TOOLS, KB_TOOLS)))
    tools = text.split("<TOOLS>", 1)[1].split("</TOOLS>", 1)[0]
    assert "Stored knowledge:\n- search_knowledge: Search stored knowledge first" in tools


def test_the_chat_runner_registers_the_search_tool():
    agent = _get_runner("gemini-2.5-flash").agent
    assert "search_knowledge" in [getattr(t, "__name__", None) for t in agent.tools]
