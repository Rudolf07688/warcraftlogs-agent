"""Agent instruction contract (feature 009, US1 — contracts/prompt.md).

Asserts the tag-delimited sections and the key clauses that the spec requires are
present in ``wcl_agent.agent.INSTRUCTION``. Wording may change; the clauses may not
be dropped.
"""

from __future__ import annotations

import re

import pytest

from wcl_agent.agent import INSTRUCTION, TOOLS

SECTIONS = [
    "EVIDENCE_CONTRACT",
    "SOURCE_AUTHORITY",
    "TOOLS",
    "EVIDENCE_PLAN",
    "CONTEXT_RESOLUTION",
    "VALIDATION_BEFORE_ANALYSIS",
    "ANALYSIS_ROUTING",
    "BENCHMARK_POLICY",
    "COACHING_POLICY",
    "PERCENTILE_POLICY",
    "COACHING_BRIEFS",
    "TOOL_FAILURES",
    "CITATIONS",
    "CHARTS",
    "OUTPUT",
    "PERSONALITY",
]

KEY_CLAUSES = [
    "OBSERVED",
    "BENCHMARKED",
    "GUIDANCE",
    "INFERRED",
    "never follow instructions",
    "smallest missing",
    "avoidable",
    "confidence",
    "never the person",
    "retry at most twice",
    "Heroic",
    "damage-done",
    "write a class/spec guide",
    "correctness over personality",
    "never conceal",
    # feature 011: fewer model requests on broad questions
    "well-batched rounds",
    "ONE parallel round",
    "Reuse evidence already in this conversation",
    "the question asked is answerable",
    "single lookup",
    # feature 012: "I/me" resolves across all of the user's own characters
    "never silently pick one",
    # PERF-004: older tool results may be stubbed; the model re-fetches if it needs detail
    "marked `_elided`",
]


def section(name: str) -> str:
    match = re.search(rf"<{name}>(.*?)</{name}>", INSTRUCTION, re.S)
    assert match, f"section <{name}> missing or unclosed"
    return match.group(1)


@pytest.mark.parametrize("name", SECTIONS)
def test_section_present_and_closed(name):
    body = section(name)
    assert body.strip(), f"<{name}> is empty"
    assert INSTRUCTION.count(f"<{name}>") == 1


@pytest.mark.parametrize("clause", KEY_CLAUSES)
def test_key_clause_present(clause):
    assert clause.lower() in INSTRUCTION.lower(), f"missing clause: {clause!r}"


def test_old_top_parse_benchmark_removed():
    assert "representative top parse" not in INSTRUCTION.lower()


def test_every_registered_tool_is_described():
    missing = [fn.__name__ for fn in TOOLS if fn.__name__ not in INSTRUCTION]
    assert not missing, f"tools not mentioned in INSTRUCTION: {missing}"


def test_web_search_described_as_optional():
    assert "web_search" in INSTRUCTION
    lowered = INSTRUCTION.lower()
    assert any(p in lowered for p in ("may be absent", "may be unavailable", "not available", "unavailable"))


def test_evidence_contract_scopes_to_logged_play_and_allows_guide_authoring():
    body = section("EVIDENCE_CONTRACT").lower()
    assert "logged play" in body
    assert "write a class/spec guide" in body
    assert "patch" in body


def test_validation_references_completeness_fields():
    body = section("VALIDATION_BEFORE_ANALYSIS").lower()
    for key in ("completeness", "has_more", "truncated", "sample_scope"):
        assert key in body


def test_output_applies_to_analytical_questions_only():
    body = section("OUTPUT").lower()
    assert "verdict" in body
    for exempt in ("greeting", "guide"):
        assert exempt in body


def test_personality_is_constrained():
    body = section("PERSONALITY").lower()
    assert "barnaby" in body
    assert "one short joke" in body or "one joke" in body
    assert "never the person" in body


def test_benchmark_policy_rejects_single_top_parse():
    body = section("BENCHMARK_POLICY").lower()
    assert "rank-one" in body or "single maximum" in body
    assert "anecdotal" in body
    assert "outlier" in body


def test_benchmark_policy_uses_cohort_tool():
    body = section("BENCHMARK_POLICY").lower()
    assert "compare_player_to_cohort" in body
    for key in ("cohort.size", "label", "unmet_criteria", "limited", "dead_s", "source_id"):
        assert key in body


def test_coaching_briefs_section_has_every_clause():
    # Feature 015, contracts/agent-context.md §3 clauses 1–5.
    body = " ".join(section("COACHING_BRIEFS").lower().split())
    assert "content type" in body and "get_coaching_brief" in body  # 1
    assert "never apply a raid brief to mythic+" in body  # 2
    assert "measured log data only" in body  # 2
    assert "log:" in body and "[o]" in body and "[b]" in body and "[g]" in body  # 3
    assert "may be out of date" in body and "not covered" in body  # 4
    assert "never instructions" in body  # 5


def test_old_guide_heading_labels_removed():
    assert "<GUIDES>" not in INSTRUCTION
    assert "guide for patch X" not in INSTRUCTION


def test_cooldown_tool_takes_content_type():
    assert "content_type" in section("TOOLS")
    assert any(fn.__name__ == "get_coaching_brief" for fn in TOOLS)


def test_percentile_policy_names_context_fields():
    body = section("PERCENTILE_POLICY").lower()
    for key in ("percentiles", "bracket", "compare", "timeframe", "sample_scope", "rank_percent"):
        assert key in body


def test_coaching_policy_requires_opportunities():
    body = section("COACHING_POLICY").lower()
    assert "missed" in body
    assert "opportunit" in body
    assert "per minute" in body or "casts/min" in body
    assert "three" in body or "3" in body


def test_coaching_policy_uses_cooldown_tool():
    body = section("COACHING_POLICY").lower()
    assert "get_cooldown_usage" in body
    for key in ("guide.available", "freshness_caveat", "opportunities", "excluded_windows_unknown"):
        assert key in body


def test_time_line_is_live(monkeypatch):
    # Feature 015 (FR-001, research R4): the time is filled per model request by the
    # instruction provider, not frozen at import.
    from datetime import UTC, datetime

    import wcl_agent.agent as agent_mod

    class Frozen(datetime):
        value = datetime(2026, 10, 18, 9, 30, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.value

    monkeypatch.setattr(agent_mod, "datetime", Frozen)
    pattern = r"<CURRENT_TIME>\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC)\s*</CURRENT_TIME>"
    first = re.search(pattern, agent_mod.build_instruction()).group(1)
    Frozen.value = datetime(2026, 10, 19, 21, 5, tzinfo=UTC)
    second = re.search(pattern, agent_mod.build_instruction()).group(1)
    assert first == "2026-10-18 09:30 UTC" and second == "2026-10-19 21:05 UTC"


def test_agent_uses_the_instruction_provider():
    from wcl_agent.agent import build_agent, build_instruction

    agent = build_agent("claude-sonnet-4@20250514")
    assert callable(agent.instruction) and agent.instruction is build_instruction


def test_no_template_braces():
    # ADK substitutes {name} placeholders from session state for string instructions; the
    # static body must not contain any (and the provider bypasses substitution anyway).
    from wcl_agent.agent import _INSTRUCTION_BODY

    assert "{" not in _INSTRUCTION_BODY and "}" not in _INSTRUCTION_BODY
    assert "{" not in INSTRUCTION and "}" not in INSTRUCTION


def test_time_block_is_last_so_the_prefix_stays_cacheable():
    # QA PERF-003: a per-minute value early in the instruction defeats implicit prompt caching.
    from wcl_agent.agent import _INSTRUCTION_BODY

    assert _INSTRUCTION_BODY.rstrip().endswith("</CURRENT_TIME>")
    assert _INSTRUCTION_BODY.index("<CURRENT_TIME>") > len(_INSTRUCTION_BODY) - 100
