"""Feature 056 (sc-413): the runtime dashboards query recording-rule aliases only.

Dashboards query aliases, never raw OTel names, so a semantic-convention rename touches one
rules file (spec §8.3). Every metric name in a Mimir panel query must be a rule recorded in
``runtime.yaml`` or an alias another stream owns by contract (055: RED and cost).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DASHBOARDS = ROOT / "observability/grafana/dashboards/runtime"
RULES = ROOT / "observability/mimir/rules/anonymous/runtime.yaml"
# Board contract:red-aliases and contract:cost-alias (defined by 055 in red.yaml, cost.yaml).
CONTRACT_ALIASES = {"app:http_requests:rate5m", "app:http_latency:p95", "genai:cost_usd:rate5m"}
D7_UID = "wcl-app-api-llm"  # D7 evolves the starter dashboard: links to it keep working

_STRINGS = re.compile(r'"(?:[^"\\]|\\.)*"')
_MATCHERS = re.compile(r"\{[^{}]*\}")
_GROUPINGS = re.compile(r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^()]*\)")
_RANGES = re.compile(r"\[[^\]]*\]")
_NAMES = re.compile(r"[A-Za-z_:][\w:]*")
_KEYWORDS = {"by", "without", "on", "ignoring", "group_left", "group_right", "and", "or", "unless", "bool", "offset"}


def metric_names(expr: str) -> set[str]:
    """The metric names a PromQL expression reads: identifiers that aren't functions,
    keywords, label names or literals."""
    text = _RANGES.sub(" ", _GROUPINGS.sub(" ", _MATCHERS.sub(" ", _STRINGS.sub(" ", expr))))
    names = set()
    for match in _NAMES.finditer(text):
        rest = text[match.end():].lstrip()
        if rest.startswith("(") or match.group() in _KEYWORDS:
            continue
        names.add(match.group())
    return names


def recorded() -> set[str]:
    rules = yaml.safe_load(RULES.read_text())
    return {rule["record"] for group in rules["groups"] for rule in group["rules"]}


def mimir_exprs(dashboard: dict) -> list[str]:
    return [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if target.get("datasource", panel.get("datasource", {})).get("type") == "prometheus"
    ]


DASHBOARD_FILES = sorted(DASHBOARDS.glob("*.json"))


def test_d6_d7_d8_are_provisioned_and_d7_keeps_its_uid():
    uids = {json.loads(path.read_text())["uid"]: path.name for path in DASHBOARD_FILES}
    assert uids == {"wcl-api-red": "api-red.json", D7_UID: "app-api-llm.json", "wcl-rag": "rag.json"}


@pytest.mark.parametrize("path", DASHBOARD_FILES, ids=lambda p: p.name)
def test_every_mimir_query_reads_aliases_only(path):
    exprs = mimir_exprs(json.loads(path.read_text()))
    assert exprs
    allowed = recorded() | CONTRACT_ALIASES
    for expr in exprs:
        names = metric_names(expr)
        assert names, expr
        assert names <= allowed, (expr, names - allowed)


def test_the_name_scan_sees_raw_series():
    """The check itself: a raw OTel series in a query is found, functions and labels are not."""
    expr = 'histogram_quantile(0.95, sum by (le) (rate(http_server_duration{http_route!~"/ws/chat"}[5m]))) or vector(0)'
    assert metric_names(expr) == {"http_server_duration"}
    assert metric_names("sum_over_time(genai:tokens:rate5m[$__range]) * 60") == {"genai:tokens:rate5m"}


def test_every_contract_alias_of_056_is_recorded():
    """contract:recording-rules: 056 owns these four in runtime.yaml."""
    assert {
        "genai:tokens:rate5m",
        "genai:invoke_agent_latency:p95",
        "rag:retrieval_latency:p95",
        "cache:hit_ratio",
    } <= recorded()


def test_latency_panels_exclude_the_chat_socket_and_streaming_routes():
    d6 = json.loads((DASHBOARDS / "api-red.json").read_text())
    latency = [expr for expr in mimir_exprs(d6) if "app:http_latency:p95" in expr]
    assert latency and all('http_route!~"/ws/chat|.*/generate"' in expr for expr in latency)
