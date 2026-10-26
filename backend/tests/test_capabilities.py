"""Capability summary renderer (feature 029, sc-204; contracts/capability-summary.md).

Renderer-level checks with fake tools plus the real ``TOOLS``: generated lines follow the
groups, the backend-sized set fits the budget, and the fixed boundary lines depend on
whether a noted (profile) group is present.
"""

from __future__ import annotations

import pytest
from google.adk.tools.base_tool import BaseTool

from wcl_agent.agent import TOOLS, _build_web_search_tool
from wcl_agent.capabilities import (
    CAPABILITY_SUMMARY_MAX_CHARS,
    MAX_TOOL_LINE_CHARS,
    ToolGroup,
    render_capability_summary,
)

NO_WEB_LINE = "No web search in this session"


async def fake_alpha(x: str) -> dict:
    """Look up alpha data for x.

    A second paragraph that must not appear in the summary.
    """
    return {"x": x}


async def fake_beta(x: str) -> dict:
    """Fetch beta
    values over
    several wrapped lines."""
    return {"x": x}


async def fake_profile_tool(x: str) -> dict:
    """Propose a change to the user's profile for approval on the card; nothing is written until then. The user can also edit the profile page directly if they prefer to do it by hand instead."""
    return {"x": x}


class FakeBaseTool(BaseTool):
    """A minimal BaseTool stand-in (as the web_search AgentTool is)."""

    def __init__(self) -> None:
        super().__init__(name="fake_search", description="Searches the web.\n\nExtra detail.")


def lines_of(text: str) -> list[str]:
    return text.splitlines()


def tool_lines(text: str) -> list[str]:
    return [line for line in lines_of(text) if line.startswith("- ")]


def test_added_tool_appears_and_removed_tool_disappears():
    without = render_capability_summary([ToolGroup("Group", (fake_alpha,))], web_search=True)
    with_beta = render_capability_summary(
        [ToolGroup("Group", (fake_alpha, fake_beta))], web_search=True
    )
    assert "- fake_beta:" not in without
    assert "- fake_beta: Fetch beta values over several wrapped lines." in with_beta
    # Only the tool line differs: no prose edit.
    assert [x for x in lines_of(with_beta) if x not in lines_of(without)] == [
        "- fake_beta: Fetch beta values over several wrapped lines."
    ]


def test_only_first_paragraph_is_used():
    text = render_capability_summary([ToolGroup("Group", (fake_alpha,))], web_search=True)
    assert "- fake_alpha: Look up alpha data for x." in text
    assert "second paragraph" not in text


def test_group_header_and_note():
    text = render_capability_summary(
        [ToolGroup("Plain", (fake_alpha,)), ToolGroup("Profile", (fake_beta,), note="propose only")],
        web_search=True,
    )
    assert "\nPlain:\n" in text
    assert "\nProfile (propose only):\n" in text


def test_base_tool_renders_via_name_and_description():
    text = render_capability_summary([ToolGroup("External", (FakeBaseTool(),))], web_search=True)
    assert "- fake_search: Searches the web." in text
    assert "Extra detail" not in text


def test_every_registered_tool_has_a_docstring():
    missing = [fn.__name__ for fn in TOOLS if not (fn.__doc__ or "").strip()]
    assert missing == []


def test_every_real_tool_gets_a_line():
    text = render_capability_summary([ToolGroup("WCL", tuple(TOOLS))], web_search=True)
    for fn in TOOLS:
        assert f"- {fn.__name__}: " in text


def test_web_search_flag():
    groups = [ToolGroup("Group", (fake_alpha,))]
    assert NO_WEB_LINE in render_capability_summary(groups, web_search=False)
    assert NO_WEB_LINE not in render_capability_summary(groups, web_search=True)


def test_without_noted_group_no_change_or_app_lines():
    text = render_capability_summary([ToolGroup("Group", (fake_alpha,))], web_search=True)
    assert "You can change" not in text
    assert "In the app" not in text
    assert "You cannot change any app data (profile, friends, guild, settings)." in text
    assert "You cannot:" not in text


def test_noted_group_gives_change_app_and_cannot_lines():
    text = render_capability_summary(
        [ToolGroup("Profile", (fake_profile_tool,), note="propose only")], web_search=True
    )
    assert "You can change, when the user asks:" in text
    assert "only by proposing the change" in text
    assert "In the app (the user does these themselves): the Profile page" in text
    assert text.rstrip().endswith("or write anything without the user's approval.")
    assert "You cannot change any app data" not in text


def test_long_first_paragraph_is_cut_at_a_sentence_end():
    line = tool_lines(render_capability_summary([ToolGroup("G", (fake_profile_tool,))], web_search=True))[0]
    assert len(line) <= MAX_TOOL_LINE_CHARS
    assert line.endswith("nothing is written until then.")


def test_long_paragraph_without_sentence_end_is_cut_at_a_word():
    async def run_on(x: str) -> dict:
        """one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twentyone twentytwo twentythree twentyfour twentyfive"""
        return {"x": x}

    line = tool_lines(render_capability_summary([ToolGroup("G", (run_on,))], web_search=True))[0]
    assert len(line) <= MAX_TOOL_LINE_CHARS
    assert line.startswith("- run_on: one two three")
    assert line.rsplit(" ", 1)[1] in {"twentyone", "twenty", "nineteen", "twentytwo", "twentythree"}


def test_no_braces_in_rendered_text():
    text = render_capability_summary(
        [ToolGroup("WCL", tuple(TOOLS)), ToolGroup("Profile", (fake_profile_tool,), note="n")],
        web_search=False,
    )
    assert "{" not in text
    assert "}" not in text


def test_backend_sized_set_fits_the_budget():
    web_search = _build_web_search_tool("gemini-3.6-flash")
    groups = [
        ToolGroup("WCL", tuple(TOOLS)),
        ToolGroup("External knowledge", (web_search,)),
        ToolGroup("Profile", (fake_profile_tool,), note="propose only; the user approves"),
    ]
    text = render_capability_summary(groups, web_search=True)
    assert "- web_search: " in text
    assert len(text) <= CAPABILITY_SUMMARY_MAX_CHARS
    assert all(len(line) <= MAX_TOOL_LINE_CHARS for line in tool_lines(text))


@pytest.mark.parametrize("web_search", [True, False])
def test_usage_rule_comes_first(web_search):
    text = render_capability_summary([ToolGroup("G", (fake_alpha,))], web_search=web_search)
    assert text.startswith("Use only tools exposed in this session.")
    assert "in parallel rather than one at a time." in text
