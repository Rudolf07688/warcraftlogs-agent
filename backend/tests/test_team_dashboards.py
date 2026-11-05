"""Build dashboards D1 and D2 (feature 055, sc-408): aliases only, cost labelled, links."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[2] / "observability" / "grafana" / "dashboards" / "build"
D1, D2, D13 = "claude-code-overview.json", "agent-team.json", "agent-team-improvement.json"
# Raw metric families the build dashboards must never name: they go through recording rules.
RAW = re.compile(r"\b(claude_code_\w+|gen_ai_\w+|traces_\w+)\b")


def load(name: str) -> dict:
    return json.loads((BUILD / name).read_text())


def panels(d: dict) -> list[dict]:
    out = []
    for p in d["panels"]:
        out.append(p)
        out.extend(p.get("panels", []))
    return out


def mimir_exprs(d: dict) -> list[tuple[str, str]]:
    return [(p["title"], t["expr"]) for p in panels(d) for t in p.get("targets", [])
            if (t.get("datasource") or p.get("datasource") or {}).get("uid") == "mimir"]


# D1's event counts take increase() of the raw counter (board scope:055-fix:counts): a
# recording-rule copy misses the created-time zero sample, a rate alias summed over the range
# gives fractions. The only raw names the build dashboards may use.
COUNTS = {
    "Sessions started": "claude_code_session_count",
    "Active time": "claude_code_active_time_total",
    "Lines of code": "claude_code_lines_of_code_count",
    "Commits": "claude_code_commit_count",
    "Pull requests": "claude_code_pull_request_count",
}
COUNT_EXPR = re.compile(r"^(round\()?sum\(increase\((claude_code_\w+)"
                        r'\{service_name="claude-code", service_namespace="wcl-agent"\}\[\$__range\]\)\)(\))?$')


@pytest.mark.parametrize("name", [D1, D2])
def test_metric_panels_query_aliases_only(name: str) -> None:
    exprs = mimir_exprs(load(name))
    assert exprs
    for title, expr in exprs:
        if name == D1 and title in COUNTS:
            continue
        assert not RAW.search(expr), f"{name} '{title}' names a raw metric: {expr}"
        assert "cc:" in expr or "team_" in expr, f"{name} '{title}' uses no alias: {expr}"


def test_d1_counts_are_whole_increases_of_the_raw_counter() -> None:
    stats = {p["title"]: p for p in panels(load(D1)) if p["type"] == "stat"}
    assert set(COUNTS) <= set(stats)
    for title, metric in COUNTS.items():
        (t,) = stats[title]["targets"]
        m = COUNT_EXPR.match(t["expr"])
        assert m and m.group(2) == metric, f"'{title}': {t['expr']}"
        # Counts are whole numbers; active time is seconds and stays as it is.
        assert bool(m.group(1)) == bool(m.group(3)) == (title != "Active time"), f"'{title}': {t['expr']}"


def top_level_operators(expr: str) -> list[str]:
    """The binary arithmetic operators outside any (), {} or [] and outside strings."""
    expr = re.sub(r'"(?:[^"\\]|\\.)*"', '""', expr)
    ops, depth = [], 0
    for ch in expr:
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        elif depth == 0 and ch in "*/+-%^":
            ops.append(ch)
    return ops


@pytest.mark.parametrize("expr", ["a * 60 / b * 60", "a / b * 60", "a * 60 / b", "a / b + c"])
def test_top_level_operators_flags_bad_ratio_shapes(expr: str) -> None:
    assert top_level_operators(expr) != ["/"]


@pytest.mark.parametrize("name", [D1, D2])
def test_ratio_panels_divide_two_totals_and_nothing_else(name: str) -> None:
    """A percentunit panel is A / B at the top level, or a single aggregate. PromQL's * and /
    associate left, so `sum(A) * 60 / sum(B) * 60` showed 3600 x A/B (QA BUG-002)."""
    ratios = [(p["title"], t["expr"]) for p in panels(load(name)) for t in p.get("targets", [])
              if p.get("fieldConfig", {}).get("defaults", {}).get("unit") == "percentunit"]
    assert ratios
    for title, expr in ratios:
        assert top_level_operators(expr) in ([], ["/"]), f"{name} '{title}': {expr}"


@pytest.mark.parametrize("name", [D1, D2, D13])
def test_ratio_time_series_sit_on_a_fixed_0_to_1_axis(name: str) -> None:
    """sc-508: an all-zero ratio series otherwise auto-scales its percent axis to 0..10000 %."""
    for p in panels(load(name)):
        defaults = p.get("fieldConfig", {}).get("defaults", {})
        if p["type"] == "timeseries" and defaults.get("unit") == "percentunit":
            assert (defaults.get("min"), defaults.get("max")) == (0, 1), f"{name} '{p['title']}'"


def test_cache_hit_ratio_leaves_output_tokens_out() -> None:
    """Spec §5.5: cacheRead / (input + cacheRead + cacheCreation), in the rule and the panels."""
    rule = (BUILD.parents[2] / "mimir" / "rules" / "anonymous" / "build.yaml").read_text()
    body = rule.split("record: cc:cache_hit_ratio", 1)[1].split("- record:", 1)[0]
    num, den = body.split("/ sum", 1)
    assert 'type="cacheRead"' in num and 'cc:tokens:rate5m{type!="output"}' in den
    for name in (D1, D2):
        (expr,) = [e for t, e in mimir_exprs(load(name)) if t == "Cache hit ratio"]
        num, den = expr.split(" / ", 1)
        assert 'type="cacheRead"' in num and 'type!="output"' in den, f"{name}: {expr}"


@pytest.mark.parametrize("name", [D1, D2])
def test_loki_panels_skip_the_content_stream(name: str) -> None:
    """No build panel reads content: the selector excludes the content stream by its index
    label, so Loki never scans it (QA PERF-004), and a sender spoofing team-board, which lands
    there, stays off the board panel (QA SEC-002)."""
    for p in panels(load(name)):
        for t in p.get("targets", []):
            if (t.get("datasource") or p.get("datasource") or {}).get("uid") == "loki":
                selector = t["expr"].split("}", 1)[0]
                assert 'content!="true"' in selector, f"{name} '{p['title']}': {t['expr']}"


@pytest.mark.parametrize("name", [D1, D2])
def test_every_cost_panel_says_estimated_list_price(name: str) -> None:
    cost = [p for p in panels(load(name))
            if (p.get("fieldConfig", {}).get("defaults", {}).get("unit") == "currencyUSD")]
    assert cost
    for p in cost:
        assert "estimated, list price" in p["title"], p["title"]


def test_d1_keeps_its_uid_and_d2_links_both_ways_with_d13() -> None:
    d1, d2, d13 = load(D1), load(D2), load(D13)
    assert d1["uid"] == "wcl-cc-overview"
    assert d2["uid"] == "wcl-agent-team"
    assert any(link.get("url") == "/d/wcl-team-improvement" for link in d2["links"])
    assert any(link.get("url") == "/d/wcl-agent-team" for link in d13["links"])


def test_d2_shows_cost_by_model_agent_and_seat() -> None:
    exprs = " ".join(e for _, e in mimir_exprs(load(D2)))
    assert "by (agent_name" in exprs and "model" in exprs
    assert "team_seat_cost_usd" in exprs and "seat" in exprs


@pytest.mark.parametrize(("title", "alias"), [
    ("Cost over time (estimated, list price)", "cc:cost_usd:rate5m"),
    ("Tokens over time", "cc:tokens:rate5m"),
])
def test_d1_over_time_panels(title: str, alias: str) -> None:
    """Owner's request (board steer:overview-panels): totals near the top, full width, bars per
    interval plus a running total on the right axis, never empty at short ranges."""
    p = next(p for p in panels(load(D1)) if p["title"] == title)
    assert p["gridPos"]["w"] == 24 and p["gridPos"]["y"] <= 16  # right below the stat rows
    assert p["interval"] == "1m"  # rules evaluate every minute
    (t,) = p["targets"]
    assert alias in t["expr"] and t["expr"].startswith("sum(") and " by (" not in t["expr"]
    (calc,) = [x for x in p["transformations"] if x["id"] == "calculateField"]
    opts = calc["options"]
    assert opts["mode"] == "cumulativeFunctions" and opts["cumulative"] == {"field": t["legendFormat"], "reducer": "sum"}
    assert p["fieldConfig"]["defaults"]["custom"]["drawStyle"] == "bars"
    (line,) = p["fieldConfig"]["overrides"]
    assert line["matcher"]["options"] == opts["alias"]
    props = {x["id"]: x["value"] for x in line["properties"]}
    assert props["custom.drawStyle"] == "line" and props["custom.axisPlacement"] == "right"
