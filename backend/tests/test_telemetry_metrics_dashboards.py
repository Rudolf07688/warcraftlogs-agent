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


def mimir_targets(dashboard: dict) -> list[tuple[dict, str]]:
    return [
        (panel, target["expr"])
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if target.get("datasource", panel.get("datasource", {})).get("type") == "prometheus"
    ]


def mimir_exprs(dashboard: dict) -> list[str]:
    return [expr for _, expr in mimir_targets(dashboard)]


# QA fix (live check #68 d): a count over the range comes from increase() on the raw counter or
# histogram, in a stat or table only. A rate alias sums to fractions (each event is smeared over
# five evaluations, and the alias never sees the created-time zero sample).
RANGE_INCREASE = re.compile(r"increase\(([A-Za-z_:][\w:]*)(?:\{[^{}]*\})?\[\$__range\]\)")
RAW_COUNTED = {
    "traces_spanmetrics_calls",
    "gen_ai_invoke_agent_duration",
    "gen_ai_execute_tool_duration",
    "app_rag_retrieval_duration",
    "app_cache_requests",
}
# Amounts, not counts: a fraction of a token is noise on hundreds of thousands.
AMOUNT_ALIASES = {"genai:tokens:rate5m"}
_SUM_OVER_TIME = re.compile(r"sum_over_time\(([A-Za-z_:][\w:]*)")


def counted_raw(panel: dict, expr: str) -> tuple[set[str], str]:
    """Raw names a stat or table counts with increase() over the range, and the expression
    without them."""
    if panel["type"] not in ("stat", "table"):
        return set(), expr
    return {m.group(1) for m in RANGE_INCREASE.finditer(expr)}, RANGE_INCREASE.sub("increase(x[1m])", expr)


DASHBOARD_FILES = sorted(DASHBOARDS.glob("*.json"))


def test_d6_d7_d8_are_provisioned_and_d7_keeps_its_uid():
    uids = {json.loads(path.read_text())["uid"]: path.name for path in DASHBOARD_FILES}
    assert uids == {"wcl-api-red": "api-red.json", D7_UID: "app-api-llm.json", "wcl-rag": "rag.json"}


@pytest.mark.parametrize("path", DASHBOARD_FILES, ids=lambda p: p.name)
def test_every_mimir_query_reads_aliases_only(path):
    targets = mimir_targets(json.loads(path.read_text()))
    assert targets
    allowed = recorded() | CONTRACT_ALIASES
    for panel, expr in targets:
        raw, rest = counted_raw(panel, expr)
        assert raw <= RAW_COUNTED, (expr, raw - RAW_COUNTED)
        names = (metric_names(rest) - {"x"}) | raw
        assert names, expr
        assert names - raw <= allowed, (expr, names - raw - allowed)


@pytest.mark.parametrize("path", DASHBOARD_FILES, ids=lambda p: p.name)
def test_counts_over_the_range_are_whole_increases_of_the_raw_series(path):
    for panel, expr in mimir_targets(json.loads(path.read_text())):
        assert set(_SUM_OVER_TIME.findall(expr)) <= AMOUNT_ALIASES, (panel["title"], expr)
        if counted_raw(panel, expr)[0]:
            assert expr.startswith("round("), (panel["title"], expr)
            assert panel["fieldConfig"]["defaults"].get("decimals") == 0, panel["title"]


@pytest.mark.parametrize("path", DASHBOARD_FILES, ids=lambda p: p.name)
def test_ratios_are_fractions_on_a_fixed_axis(path):
    """Live check #68 c: an all-zero ratio auto-scaled its percent axis to 0..10000 %."""
    for panel, expr in mimir_targets(json.loads(path.read_text())):
        defaults = panel["fieldConfig"]["defaults"]
        assert defaults.get("unit") != "percent", panel["title"]  # ratios are 0..1, percentunit
        if defaults.get("unit") != "percentunit":
            continue
        assert "100" not in expr, (panel["title"], expr)
        if panel["type"] == "timeseries":
            assert (defaults.get("min"), defaults.get("max")) == (0, 1), panel["title"]


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
    for quantile in ("p50", "p95", "p99"):
        latency = [expr for expr in mimir_exprs(d6) if f"app:http_latency:{quantile}" in expr]
        assert latency and all('http_route!~"/ws/chat|.*/generate"' in expr for expr in latency), quantile


# --- feature 059 (sc-462) ----------------------------------------------------------------

DATASOURCES = ROOT / "observability/grafana/provisioning/datasources/datasources.yaml"


def test_the_059_aliases_are_recorded_and_on_their_dashboards():
    assert {
        "app:http_latency:p50",
        "app:http_latency:p99",
        "genai:finish_reasons:rate5m",
        "genai:turns_per_conversation:p50",
        "genai:turns_per_conversation:p95",
        "rag:embedding_latency:p95",
        "rag:embedding_batch_size:avg5m",
    } <= recorded()
    on = {
        name: " ".join(mimir_exprs(json.loads((DASHBOARDS / name).read_text())))
        for name in ("api-red.json", "app-api-llm.json", "rag.json")
    }
    assert "app:http_latency:p50" in on["api-red.json"] and "app:http_latency:p99" in on["api-red.json"]
    assert "genai:finish_reasons:rate5m" in on["app-api-llm.json"]
    assert "genai:turns_per_conversation:p95" in on["app-api-llm.json"]
    assert "rag:embedding_latency:p95" in on["rag.json"] and "rag:embedding_batch_size:avg5m" in on["rag.json"]


def test_the_059_rules_read_only_allowlisted_labels():
    """The new aliases group by the OTLP-translated names of allowlisted attributes only."""
    from backend.app.telemetry.setup import METRIC_ATTRIBUTES

    translated = {name.replace(".", "_") for name in METRIC_ATTRIBUTES} | {"service_name", "le", "http_route"}
    for group in yaml.safe_load(RULES.read_text())["groups"]:
        for rule in group["rules"]:
            if rule["record"].startswith(("genai:finish", "genai:turns", "rag:embedding", "app:http_latency")):
                for grouping in re.findall(r"\bby \(([^()]*)\)", rule["expr"]):
                    assert {label.strip() for label in grouping.split(",")} <= translated, rule["record"]


def test_d6_has_the_service_graph_from_tempo():
    d6 = json.loads((DASHBOARDS / "api-red.json").read_text())
    [graph] = [p for p in d6["panels"] if p["type"] == "nodeGraph"]
    assert graph["datasource"] == {"type": "tempo", "uid": "tempo"}
    assert [t["queryType"] for t in graph["targets"]] == ["serviceMap"]
    tempo = next(d for d in yaml.safe_load(DATASOURCES.read_text())["datasources"] if d["uid"] == "tempo")
    assert tempo["jsonData"]["serviceMap"] == {"datasourceUid": "mimir"}


# sc-471: a panel that shows one bar per interval, or totals in its legend, must read windows
# equal to its step, or neighbouring windows overlap and the bars or totals overcount.
_WINDOWS = re.compile(r"\[([^\]:]+)(?::[^\]]*)?\]")


def per_interval(panel: dict) -> bool:
    defaults = panel.get("fieldConfig", {}).get("defaults", {})
    bars = defaults.get("custom", {}).get("drawStyle") == "bars"
    totals = bool(set(panel.get("options", {}).get("legend", {}).get("calcs", [])) & {"sum", "count", "total"})
    return bars or totals


def windows_equal_the_step(panel: dict) -> bool:
    for target in panel.get("targets", []):
        if "expr" not in target:
            continue
        if any(window != "$__interval" for window in _WINDOWS.findall(target["expr"])):
            return False
        if _WINDOWS.findall(target["expr"]) and target.get("interval") in (None, ""):
            return False
    return True


@pytest.mark.parametrize("path", DASHBOARD_FILES, ids=lambda p: p.name)
def test_per_interval_bars_and_legend_totals_use_a_window_equal_to_the_step(path):
    for panel in json.loads(path.read_text())["panels"]:
        if per_interval(panel):
            assert windows_equal_the_step(panel), panel["title"]


def test_the_window_check_catches_an_overlapping_window():
    """The check itself (sc-471): 5-minute windows under 1-minute bars overcount."""
    bars = {"fieldConfig": {"defaults": {"custom": {"drawStyle": "bars"}}}, "options": {}}
    overlapping = {**bars, "targets": [{"expr": "sum(increase(x[5m]))", "interval": "1m"}]}
    stepped = {**bars, "targets": [{"expr": "sum(increase(x[$__interval]))", "interval": "1m"}]}
    totals = {"fieldConfig": {"defaults": {}}, "options": {"legend": {"calcs": ["sum"]}}, "targets": overlapping["targets"]}
    assert per_interval(overlapping) and not windows_equal_the_step(overlapping)
    assert per_interval(totals) and not windows_equal_the_step(totals)
    assert windows_equal_the_step(stepped)
    assert not per_interval({"fieldConfig": {"defaults": {"custom": {"drawStyle": "line"}}}, "options": {}})
