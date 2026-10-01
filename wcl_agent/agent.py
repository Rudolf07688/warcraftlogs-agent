"""The ADK root agent: a Warcraft Logs combat-log analyst powered by Gemini."""

from __future__ import annotations

import logging
import os
from datetime import datetime as dt

from google.adk.agents import Agent
from google.adk.models.registry import LLMRegistry
from google.adk.planners import BuiltInPlanner
from google.adk.tools import google_search
from google.adk.tools.agent_tool import AgentTool
from google.genai import types as genai_types

logger = logging.getLogger(__name__)

# Register Anthropic-on-Vertex (Claude) so `Agent(model="claude-…")` resolves to
# the Claude LLM class; Gemini ids pass through as plain strings (US4). Safe no-op
# if the optional anthropic dependency isn't installed.
try:
    from google.adk.models.anthropic_llm import Claude

    LLMRegistry.register(Claude)
except Exception as exc:  # noqa: BLE001
    logger.warning("Anthropic (Claude) model class not registered: %s", exc)

from .report_tools import (
    get_character_encounter_rankings,
    get_character_zone_rankings,
    get_report_events,
    get_report_fights,
    get_report_graph,
    get_report_master_data,
    get_report_player_details,
    get_report_rankings,
    get_report_table,
    run_wcl_graphql,
)
from .tools import (
    check_rate_limit,
    compare_specs,
    find_encounter,
    get_rankings_distribution,
    get_selected_encounter,
    get_spec_options,
)

INSTRUCTION = f"""
You are a World of Warcraft combat-log analyst with full access to the Warcraft
Logs v2 API. Your job is to answer ANY question the data can support — from
high-level "how are hunters performing" down to "which spells make up this
player's damage on this pull".

--- The current time is: {dt.now().strftime("%Y-%m-%d %H:%M")} ---

You have three layers of tools; combine them freely:

1. LEADERBOARD (the population view for the selected encounter):
   - `get_selected_encounter` — confirm the encounter/difficulty/season first.
   - `get_spec_options` — get correct PascalCase class/spec filter values.
   - `get_rankings_distribution` / `compare_specs` — score percentiles and spec
     comparisons. Each top parse includes a `report_code` and `fight_id` — use
     those to drill deeper.

2. REPORT DEEP-DIVE (one specific log; this is where detailed answers live):
   - `get_report_fights` — turn a report_code into fight IDs + player source IDs.
   - `get_report_table` — THE workhorse. Breaks a fight down by ability and
     source: damage/healing (set source_id to see WHICH SPELLS make up a
     player's damage), casts, buff/debuff uptime, deaths, damage taken, etc.
   - `get_report_events` — raw event stream for granular timing questions.
   - `get_report_graph` — time-series (DPS/HPS/resources over time).
   - `get_report_rankings` / `get_report_player_details` — parse %s, gear, talents.
   - `get_report_master_data` — resolve actor/ability ids to names.

3. INDIVIDUAL PLAYERS:
   - `get_character_zone_rankings` / `get_character_encounter_rankings` — one
     player's parse history.

ESCAPE HATCH:
   - `run_wcl_graphql` — for anything above tools don't cover, write a raw
     GraphQL query yourself (roots: worldData, reportData, characterData,
     guildData, gameData, rateLimitData). Use this rather than saying you can't.

CONTEXT RESOLUTION (do this first for leaderboard questions):
- There may be NO pre-selected encounter. If `get_selected_encounter` errors, call
  `find_encounter` with the boss name the user mentioned, choose the matching
  `encounter_id`, pick the `difficulty_id` (Mythic 5, Heroic 4, Normal 3, LFR 1),
  and pass BOTH to `get_rankings_distribution` / `compare_specs`.
- If the user didn't state a difficulty, default to Heroic (4) and say so.

WARCRAFT LOGS DOMAIN KNOWLEDGE:
- Percentiles are the currency: a parse's percentile = how it ranks vs all logged
  parses for that class/spec/encounter/difficulty. WCL color brackets: grey <25,
  green 25–49, blue 50–74, purple 75–94, orange 95–98, pink 99, gold 100. Translate
  numbers into these when it helps.
- Metrics: `dps` = damage/sec (damage dealers), `hps` = healing/sec (healers),
  `bossdps` isolates boss damage (single-target), `rdps` credits raid-buff support.
  Default to `dps` unless the question is about healing.
- Difficulties: Mythic(5) > Heroic(4) > Normal(3) > LFR(1); harder = fewer, higher-
  skill parses.
- Item level (`bracketData`/`item_level`) inflates parses — higher gear, higher numbers.

ANALYSIS PLAYBOOKS:
- "How is <class/spec> performing?" → `get_rankings_distribution` (or `compare_specs`
  for a whole class). Report median, p95, max, the spec ranking, and sample size.
- "How do I improve / why is my parse low?" → take a representative TOP parse
  (`report_code` + `fight_id` from the distribution), then compare the player to it:
  `get_report_table` DamageDone by `source_id` (ability breakdown), Casts
  (rotation/APM), Buffs/Debuffs (key uptimes), Deaths. Call out concrete gaps.
- "Why did we wipe / who died?" → `get_report_table` Deaths + DamageTaken for the pull.
- Comparisons → fetch each side in parallel, then contrast concrete numbers.

Method:
- To answer an ability/spell breakdown: get a representative parse from
  `get_rankings_distribution` (note its report_code + fight_id), then call
  `get_report_table` with data_type 'DamageDone' (or 'Healing') and source_id set
  to that player to see their per-ability contribution. Use `get_report_fights`
  if you need to map names to source IDs.
- Base every answer ONLY on data the tools return; never invent numbers.
- Explain percentiles plainly and always state sample size / that leaderboard
  data is the current-season top-of-distribution.
- If a tool errors, read the message, adjust filters (or fix your GraphQL) and
  retry; check `check_rate_limit` if you suspect the API budget.
- Keep reports tight, concrete, and scannable.
- When a question needs several independent Warcraft Logs lookups (e.g. comparing
  specs or several encounters), issue those tool calls together in parallel rather
  than one at a time, so the data is gathered concurrently.

WEB SEARCH:
- If a `web_search` tool is available and a question needs current or external
  information the Warcraft Logs data can't provide (patch notes, class guides,
  recent meta changes, news), call `web_search` with a focused query and cite what
  it returns. If no web tool is available, answer from the data you can access and
  say so rather than guessing.
""".strip()

# Single source of truth for the default model id: the same WCL_DEFAULT_MODEL env
# that backend config reads, so the CLI/root_agent fallback can't drift from the
# backend's runtime default (US4 / F2). The backend always passes an explicit,
# startup-validated model from app.state; this constant is only a last resort.
DEFAULT_MODEL = os.getenv("WCL_DEFAULT_MODEL", "gemini-3.6-flash")

# Name of the grounding sub-agent; also the tool name the model calls and the
# signal the backend uses to surface a "used web search" indicator (US3).
WEB_SEARCH_AGENT_NAME = "web_search"

# Single source of truth for the agent's tools (reused by every model variant).
TOOLS = [
    # Leaderboard / population
    get_selected_encounter,
    find_encounter,
    get_spec_options,
    get_rankings_distribution,
    compare_specs,
    # Report deep-dive
    get_report_fights,
    get_report_table,
    get_report_events,
    get_report_graph,
    get_report_rankings,
    get_report_player_details,
    get_report_master_data,
    # Individual characters
    get_character_zone_rankings,
    get_character_encounter_rankings,
    # Utility / escape hatch
    check_rate_limit,
    run_wcl_graphql,
]


def _is_anthropic(model: str) -> bool:
    """Anthropic-on-Vertex ids (Claude) vs Gemini ids."""
    return "claude" in model.lower()


def _build_web_search_tool(model: str) -> AgentTool:
    """Wrap a grounding-only Gemini agent as a callable `web_search` tool.

    Native Google Search grounding is exposed via a sub-agent rather than adding
    the built-in `google_search` tool directly to the root agent: some Gemini
    generations reject combining `google_search` with many function tools in one
    request, and this keeps all 16 WCL function tools intact. It also matches the
    original "web-search sub-agent as a tool" intent. ``propagate_grounding_metadata``
    surfaces the sub-agent's grounding signal to the parent event stream so the UI
    can show a "used web search" indicator (US3/FR-011).
    """
    search_agent = Agent(
        name=WEB_SEARCH_AGENT_NAME,
        model=model,
        description="Searches the web with Google Search and returns a concise, cited answer.",
        instruction=(
            "You are a web search assistant. Use Google Search to find current, "
            "accurate information for the given query and return a concise summary "
            "with the key facts and their source titles/links."
        ),
        tools=[google_search],
    )
    return AgentTool(agent=search_agent, propagate_grounding_metadata=True)


def build_agent(model: str = DEFAULT_MODEL) -> Agent:
    """Build the WCL analyst agent for a given model id (DRY factory).

    Gemini models get web grounding (via the `web_search` sub-agent tool);
    Anthropic-on-Vertex (and any non-grounding) models run with the WCL tools only
    and degrade gracefully without web access (US3/FR-012).
    """
    tools = list(TOOLS)
    if not _is_anthropic(model):
        tools.append(_build_web_search_tool(model))
    return Agent(
        name="wcl_agent",
        model=model,
        description="Analyzes Warcraft Logs ranking and report data for any question.",
        instruction=INSTRUCTION,
        tools=tools,
        # Native thinking planner — fits Gemini 3.x thinking models (unlike the
        # ReAct text planner, which fights them). Reasoning is returned as separate
        # `thought` parts that the backend filters out of the streamed answer.
        planner=BuiltInPlanner(
            thinking_config=genai_types.ThinkingConfig(include_thoughts=True)
        ),
    )


# Default agent (used by the terminal CLI and `adk` tooling).
root_agent = build_agent()
