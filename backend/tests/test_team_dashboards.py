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


@pytest.mark.parametrize("name", [D1, D2])
def test_metric_panels_query_aliases_only(name: str) -> None:
    exprs = mimir_exprs(load(name))
    assert exprs
    for title, expr in exprs:
        assert not RAW.search(expr), f"{name} '{title}' names a raw metric: {expr}"
        assert "cc:" in expr or "team_" in expr, f"{name} '{title}' uses no alias: {expr}"


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
