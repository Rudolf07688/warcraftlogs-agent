"""Generated capability summary for the agent instruction (feature 029, sc-204).

Design C1-C4 and decision D13 (documentation/designs/self-aware-agent/capabilities-and-tools.html).
The ``<TOOLS>`` section of the instruction is rendered from the tool groups that are
registered on the agent, so the summary and the registered list cannot drift apart: a tool
added to a group shows up with its docstring's first paragraph, with no prose edit.

This module must not import ``wcl_agent.agent`` (that module imports this one).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.function_tool import FunctionTool

# Budget for the whole rendered summary and for each tool line (asserted by tests).
CAPABILITY_SUMMARY_MAX_CHARS = 4000
MAX_TOOL_LINE_CHARS = 160

_USAGE_RULE = (
    "Use only tools exposed in this session. Combine them freely; when a question needs several "
    "independent lookups (several specs, encounters, or players), issue those tool calls together "
    "in parallel rather than one at a time."
)
_NO_WEB_SEARCH = (
    "No web search in this session: say that current-patch verification was not possible."
)
# What the agent may change, and only through a proposal card the user approves (D13).
_CAN_CHANGE = (
    "You can change, when the user asks: their own characters and friends, including raid roles, "
    "only by proposing the change; nothing is written until the user approves it on the card."
)
_APP_FACTS = (
    "In the app (the user does these themselves): the Profile page (own characters, friends, main "
    "guild, raid roles; Class guides tab), recent raids and Mythic+ runs on the welcome screen, "
    "PDF download of a reply, boss checkboxes under a report to focus the next question, and the "
    "model picker."
)
_CANNOT_WITH_PROFILE = (
    "You cannot: change the guild, settings, conversations or other users' data, or write "
    "anything without the user's approval."
)
_CANNOT_READ_ONLY = "You cannot change any app data (profile, friends, guild, settings)."


@dataclass(frozen=True)
class ToolGroup:
    """A labelled set of tools: plain async functions or ADK ``BaseTool`` instances.

    ``note`` is a group rule shown in the header; only the backend's profile group sets one,
    which also switches on the can-change and app-facts lines.
    """

    label: str
    tools: tuple
    note: str = ""


def _name_and_description(tool) -> tuple[str, str]:
    """The name and description ADK itself sends to the model for this tool."""
    adk_tool = tool if isinstance(tool, BaseTool) else FunctionTool(tool)
    return adk_tool.name, adk_tool.description or ""


def _first_paragraph(text: str) -> str:
    """First paragraph of a description, whitespace-collapsed."""
    return " ".join(re.split(r"\n\s*\n", text.strip(), maxsplit=1)[0].split())


def _fit(text: str, budget: int) -> str:
    """Cut ``text`` to ``budget`` chars: at the last sentence end that fits, else at a word."""
    if len(text) <= budget:
        return text
    sentence_ends = [m.start() + 1 for m in re.finditer(r"\. ", text) if m.start() + 1 <= budget]
    if sentence_ends:
        return text[: sentence_ends[-1]]
    return text[:budget].rsplit(" ", 1)[0].rstrip(" ,;:")


def _tool_line(tool) -> str:
    name, description = _name_and_description(tool)
    prefix = f"- {name}: "
    return prefix + _fit(_first_paragraph(description), MAX_TOOL_LINE_CHARS - len(prefix))


def render_capability_summary(groups: Sequence[ToolGroup], *, web_search: bool) -> str:
    """Render the plain-text capability summary for the instruction's ``<TOOLS>`` section.

    Output order: usage rule, one block per group, the no-web-search line (when
    ``web_search`` is false), the can-change and app-facts lines (only when a group has a
    note), and the cannot line (always, worded by whether a noted group is present).
    """
    has_profile = any(group.note for group in groups)
    lines = [_USAGE_RULE]
    for group in groups:
        header = f"{group.label} ({group.note}):" if group.note else f"{group.label}:"
        lines += ["", header, *(_tool_line(tool) for tool in group.tools)]
    if not web_search:
        lines += ["", _NO_WEB_SEARCH]
    if has_profile:
        lines += ["", _CAN_CHANGE, "", _APP_FACTS]
    lines += ["", _CANNOT_WITH_PROFILE if has_profile else _CANNOT_READ_ONLY]
    return "\n".join(lines)
