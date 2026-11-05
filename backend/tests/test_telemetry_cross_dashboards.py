"""Feature 060: D5 (App: Frontend) and D12 (Build vs Runtime) are well formed.

D5 reads Loki only (Faro's logfmt lines; no Loki ruler this sprint). D12 reads the cross-layer
aliases in ``cross.yaml`` and the commit facts ``observability/build-runtime/commits.py``
pushes. Any panel drawing per-interval bars or legend totals uses a window equal to the step
(sc-471: overlapping windows count an event in several bars).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
D5 = ROOT / "observability/grafana/dashboards/runtime/frontend.json"
CROSS = ROOT / "observability/grafana/dashboards/cross"

_WINDOWS = re.compile(r"\[([^\]]+)\]")
# Faro's logfmt fields D5 parses (checked against a live receiver, observability/test/frontend.sh).
D5_FIELDS = {"kind", "type", "view_name", "event_name", "event_data_model", "event_data_reason",
             "event_data_ttft_ms", "value", "context_boundary"}
D5_FIELDS |= {f"value_{v}" for v in ("lcp", "inp", "cls", "fcp", "ttfb")}
CUSTOM_EVENTS = {"agent_message_sent", "agent_first_token_rendered", "agent_response_completed", "stream_aborted"}


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def targets(dashboard: dict) -> list[tuple[dict, dict]]:
    return [(panel, target) for panel in dashboard["panels"] for target in panel.get("targets", [])]


def counts_per_interval(panel: dict) -> bool:
    """Bars, or a legend that sums the series: each point must count its own step only."""
    custom = panel.get("fieldConfig", {}).get("defaults", {}).get("custom", {})
    calcs = panel.get("options", {}).get("legend", {}).get("calcs", [])
    return custom.get("drawStyle") == "bars" or panel["type"] == "barchart" or bool({"sum", "total"} & set(calcs))


def window_is_step(panel: dict, expr: str) -> bool:
    """A range panel's windows are the step ($__auto for Loki, $__interval for Prometheus with
    the interval pinned); an instant panel counts the whole range."""
    windows = set(_WINDOWS.findall(expr))
    return bool(windows) and windows <= {"$__auto", "$__interval", "$__range"}


def test_d5_is_provisioned_under_runtime_with_its_uid():
    assert load(D5)["uid"] == "wcl-d5-frontend"


def test_d5_reads_loki_only_and_parses_known_faro_fields():
    d5 = load(D5)
    assert targets(d5)
    for panel, target in targets(d5):
        assert (target.get("datasource") or panel["datasource"])["type"] == "loki", panel["title"]
        expr = target["expr"]
        assert expr.startswith(('{service_name="web"}', "sum", "quantile_over_time", "topk")), expr
        assert '{service_name="web"}' in expr, expr
        used = set(re.findall(r"\b([a-z_]+)(?:!?=|=~)\"", expr.split("|", 1)[1])) | set(re.findall(r"\bunwrap (\w+)", expr))
        used -= {"__error__"}
        used |= {g for m in re.findall(r"\bby \(([^)]*)\)", expr) for g in m.replace(" ", "").split(",")}
        assert used <= D5_FIELDS, (panel["title"], used - D5_FIELDS)


def test_d5_covers_the_story_panels():
    d5 = load(D5)
    exprs = " ".join(t["expr"] for _, t in targets(d5))
    for vital in ("lcp", "inp", "cls"):
        assert f"unwrap value_{vital}" in exprs
    assert 'kind="exception"' in exprs and "by (type, value, view_name, context_boundary)" in exprs
    assert "quantile_over_time(0.75" in exprs and "by (view_name)" in exprs
    sent = {e for e in CUSTOM_EVENTS if f'event_name="{e}"' in exprs}
    assert sent == CUSTOM_EVENTS
    assert "agent_feedback" not in exprs  # no feedback feature (spec §7.5 reserved)


def test_unwrapped_values_drop_parse_errors():
    for panel, target in targets(load(D5)):
        if "unwrap" in target["expr"]:
            assert '__error__=""' in target["expr"], panel["title"]


def dashboards() -> list[Path]:
    return [D5, *sorted(CROSS.glob("*.json"))]


@pytest.mark.parametrize("path", dashboards(), ids=lambda p: p.name)
def test_per_interval_counts_use_a_window_equal_to_the_step(path):
    """sc-471: bars and legend totals count each event once."""
    checked = 0
    for panel, target in targets(load(path)):
        expr = target.get("expr", "")
        if target.get("queryType") == "instant" or target.get("instant"):
            assert "$__auto" not in expr and "$__interval" not in expr, (panel["title"], expr)
            continue
        if counts_per_interval(panel):
            checked += 1
            assert window_is_step(panel, expr) and "$__range" not in expr, (panel["title"], expr)
            if (target.get("datasource") or panel["datasource"])["type"] == "prometheus":
                assert panel.get("interval"), panel["title"]  # $__interval is the step only when pinned
    if path == D5:
        assert checked  # the stream-abort bars


def test_the_window_check_bites():
    bars = {"type": "timeseries", "fieldConfig": {"defaults": {"custom": {"drawStyle": "bars"}}}}
    assert counts_per_interval(bars)
    assert not window_is_step(bars, 'sum(count_over_time({service_name="web"} [5m]))')
    assert window_is_step(bars, 'sum(count_over_time({service_name="web"} [$__auto]))')
