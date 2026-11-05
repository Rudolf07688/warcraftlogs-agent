"""Feature 060: D5 (App: Frontend) and D12 (Build vs Runtime) are well formed.

D5 reads Loki only (Faro's logfmt lines; no Loki ruler this sprint). D12 reads the cross-layer
aliases in ``cross.yaml`` and the commit facts ``observability/build-runtime/commits.py``
pushes. Any panel drawing per-interval bars or legend totals uses a window equal to the step
(sc-471: overlapping windows count an event in several bars).
"""

from __future__ import annotations

import json
import re
import sys
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
        used |= {g for m in re.findall(r"\bby \(([^)]*)\)", expr) for g in m.replace(" ", "").split(",") if g}
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


def test_every_quantile_is_grouped_so_a_stat_shows_one_percentile_not_one_per_event():
    """An ungrouped quantile_over_time keeps one series per log line's own labels (timestamp,
    session_id, ...): the stat shows a tile per event. `by ()` makes it one number."""
    seen = 0
    for panel, target in targets(load(D5)):
        if target["expr"].startswith("quantile_over_time("):
            seen += 1
            assert re.search(r"\]\)\s+by \([^)]*\)$", target["expr"]), (panel["title"], target["expr"])
    assert seen


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


# --- D12: Build vs Runtime -------------------------------------------------------------------

D12 = CROSS / "build-runtime.json"
CROSS_RULES = ROOT / "observability/mimir/rules/anonymous/cross.yaml"
# Pushed by observability/build-runtime/commits.py (team.* style gauges, no unit suffix).
PUSHED = {"build_commit_info", "build_commit_cost_usd"}


def cross_recorded() -> dict[str, str]:
    import yaml

    rules = yaml.safe_load(CROSS_RULES.read_text())
    return {rule["record"]: rule["expr"] for group in rules["groups"] for rule in group["rules"]}


def test_d12_has_its_uid_in_the_cross_folder():
    assert load(D12)["uid"] == "wcl-d12-build-runtime"
    assert D12.parent.name == "cross"


def test_d12_reads_cross_aliases_and_pushed_commit_facts_only():
    from backend.tests.test_telemetry_metrics_dashboards import metric_names

    allowed = set(cross_recorded()) | PUSHED
    d12 = load(D12)
    exprs = [t["expr"] for _, t in targets(d12)] + [a["expr"] for a in d12["annotations"]["list"]]
    assert exprs
    for expr in exprs:
        names = metric_names(expr)
        assert names and names <= allowed, (expr, names - allowed)


def test_d12_overlays_commit_annotations_on_the_three_runtime_panels():
    d12 = load(D12)
    (annotation,) = d12["annotations"]["list"]
    assert "cross:running_commit:info" in annotation["expr"] and "{{commit}}" in annotation["titleFormat"]
    series = [p for p in d12["panels"] if p["type"] == "timeseries"]
    assert {metric for p in series for t in p["targets"] for metric in re.findall(r"cross:[\w:]+_by_commit", t["expr"])} == {
        "cross:http_latency:p95_by_commit", "cross:http_error_ratio:5m_by_commit", "cross:llm_cost_per_request:5m_by_commit"}


def test_d12_table_maps_commit_to_seat_cost_and_deltas_and_states_its_rules():
    d12 = load(D12)
    (table,) = [p for p in d12["panels"] if p["type"] == "table"]
    for target in table["targets"]:
        assert target["instant"] and target["format"] == "table"
        assert target["expr"].startswith("max by (commit, seat, feature)"), target["expr"]
    renames = next(t for t in table["transformations"] if t["id"] == "organize")["options"]["renameByName"]
    assert {"commit", "seat", "Value #D"} <= set(renames) and any(v.startswith("Δ") for v in renames.values())
    text = next(p for p in d12["panels"] if p["type"] == "text")["options"]["content"]
    assert "Attribution" in text and "Build cost" in text and "Runtime deltas" in text and "unattributed" in text


def test_cross_rules_join_on_the_running_version_and_record_every_by_commit_alias():
    rules = cross_recorded()
    assert 'target_info{job="wcl-agent/api"}' in rules["cross:running_version:info"]
    assert "build_commit_info" in rules["cross:commit_seat:info"]
    assert "unattributed" in rules["cross:running_commit:info"]
    for base in ("cross:http_latency:p95", "cross:http_error_ratio:5m", "cross:llm_cost_per_request:5m"):
        assert f"{base} * on (service_name) group_left" in rules[f"{base}_by_commit"]
    assert 'http_route!="/ws/chat"' in rules["cross:http_latency:p95"]  # the chat socket is excluded
    # An idle window yields no sample, never NaN or infinity (one would poison every range mean).
    assert rules["cross:http_latency:p95"].rstrip().endswith(">= 0")
    for ratio in ("cross:http_error_ratio:5m", "cross:llm_cost_per_request:5m"):
        assert 'app:http_requests:rate5m{service_name="api"}) > 0)' in rules[ratio], ratio


# --- commits.py: the attribution rule ---------------------------------------------------------


def load_commits():
    import importlib.util

    spec = importlib.util.spec_from_file_location("commits", ROOT / "observability/build-runtime/commits.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["commits"] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


def board_entry(id_: int, author: str, kind: str, key: str, refs: list[str], ts: str = "2026-11-05T12:00:00+00:00") -> dict:
    return {"id": id_, "ts": ts, "author": author, "kind": kind, "text": "", "key": key, "refs": refs}


def test_a_merge_belongs_to_the_hand_off_author_on_its_key():
    commits = load_commits()
    roster = {"tomas": "tomas (dev-2)", "maren": "maren (po)", "nils": "nils (dev-3)"}
    found = commits.attribute([
        board_entry(1, "tomas", "handoff", "status:060", ["abc1234ff"]),
        board_entry(2, "nils", "handoff", "status:059", ["1111111"]),
        board_entry(3, "maren", "merge", "status:060", ["def5678"]),
        board_entry(4, "maren", "merge", "status:qa-fix", ["2222222"]),
        board_entry(5, "tomas", "change", "status:060", ["3333333"]),  # not a hand-off or merge
        board_entry(6, "tomas", "handoff", "status:060", ["not-a-sha"]),
    ], "s", roster)
    got = {c.commit: (c.seat, c.feature) for c in found}
    assert got == {
        "abc1234": ("tomas (dev-2)", "060"),
        "1111111": ("nils (dev-3)", "059"),
        "def5678": ("tomas (dev-2)", "060"),
        "2222222": ("maren (po)", "qa-fix"),
    }


# Sprint 2026-11-05's hand-off and merge entries as the board exported them (texts cut short):
# hand-offs are keyed status:<feature> and name their head only in the text, merges are keyed
# merge:<feature> and carry the SHA as a ref. Only 1 of these 7 commits used to be attributed.
SPRINT_1105 = [
    {"id": 47, "ts": "2026-11-05T14:06:27+00:00", "author": "nils", "kind": "handoff", "key": "status:059", "refs": None,
     "text": "059 done on branch 059-runtime-profiles (base 6437aa2, head 5447873; commits 67eee52 sc-461, a468f6e sc-463"},
    {"id": 49, "ts": "2026-11-05T14:09:57+00:00", "author": "maren", "kind": "merge", "key": "merge:059", "refs": ["953a11a"],
     "text": "059 merged into sprint-2026-11-05 as 953a11a: check.py on the merged tree RESULT PASS 2243 passed"},
    {"id": 59, "ts": "2026-11-05T14:37:09+00:00", "author": "ansel", "kind": "handoff", "key": "status:058", "refs": None,
     "text": "058 done on branch 058-datastore-telemetry (base 953a11a after rebase, head 2fc9826; commits e207633 spec"},
    {"id": 66, "ts": "2026-11-05T15:04:36+00:00", "author": "tomas", "kind": "handoff", "key": "status:060", "refs": ["7068f46"],
     "text": "060 done: branch 060-frontend-build-runtime (base 953a11a after rebase, head 7068f46; commits a2e7589 sc-416"},
    {"id": 67, "ts": "2026-11-05T15:06:00+00:00", "author": "maren", "kind": "merge", "key": "merge:060", "refs": ["8ca8a3b"],
     "text": "060 merged into sprint-2026-11-05 as 8ca8a3b: verify --index REUSE (tomas receipt, 2258 passed)"},
    {"id": 69, "ts": "2026-11-05T15:12:28+00:00", "author": "ansel", "kind": "handoff", "key": "status:058", "refs": None,
     "text": "058 security rework done on 058-datastore-telemetry, rebased onto 8ca8a3b, head 3bc726d (rework commit; earlier"},
    {"id": 70, "ts": "2026-11-05T15:13:13+00:00", "author": "maren", "kind": "merge", "key": "merge:058", "refs": ["fcef188"],
     "text": "058 merged into sprint-2026-11-05 as fcef188 after its security rework: verify --index --need-pg REUSE"},
]


def test_this_sprints_board_attributes_every_hand_off_and_merge_commit():
    commits = load_commits()
    roster = {"nils": "nils (dev-3)", "ansel": "ansel (dev-1)", "tomas": "tomas (dev-2)", "maren": "maren (po)"}
    got = {c.commit: (c.seat, c.feature) for c in commits.attribute(SPRINT_1105, "2026-11-05", roster)}
    assert got == {
        "5447873": ("nils (dev-3)", "059"),  # head named in the text only
        "953a11a": ("nils (dev-3)", "059"),  # merge:059 belongs to 059's hand-off author
        "2fc9826": ("ansel (dev-1)", "058"),
        "7068f46": ("tomas (dev-2)", "060"),
        "8ca8a3b": ("tomas (dev-2)", "060"),
        "3bc726d": ("ansel (dev-1)", "058"),
        "fcef188": ("ansel (dev-1)", "058"),
    }


def test_the_running_version_prefers_a_known_version_over_unknown():
    expr = " ".join(cross_recorded()["cross:running_version:info"].split())
    # Two selectors, because timestamp() of an `or` result is the evaluation time, not a sample time.
    assert 'timestamp(target_info{job="wcl-agent/api", service_version!~"|unknown"}) or on (job) timestamp(target_info{job="wcl-agent/api"})' in expr


def test_two_seats_for_one_commit_get_different_stable_values_so_topk_has_no_tie():
    commits = load_commits()
    ts = commits.datetime.fromisoformat("2026-11-05T12:00:00+00:00")
    a = commits.Commit("abc1234", "nils (dev-3)", "059", "s", ts)
    b = commits.Commit("abc1234", "nils (dev-4)", "059", "s", ts)

    def values(cs):
        metric = commits.payload(cs)["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
        return [p["asDouble"] for p in metric["gauge"]["dataPoints"]]

    first, second = values([a, b])
    assert 1 <= first < 2 and 1 <= second < 2 and first != second
    assert values([a, b]) == [first, second]  # the same on every push: pushing again is safe


def test_a_hand_off_without_refs_takes_the_head_not_the_base_or_a_word():
    commits = load_commits()
    roster = {"nils": "nils (dev-3)"}
    text = "done (base 1234567, head abcdef1; added decade defaced notes)"
    (c,) = commits.attribute([board_entry(1, "nils", "handoff", "status:070", []) | {"text": text}], "s", roster)
    assert c.commit == "abcdef1"
    no_head = "done (base 1234567), the tip is deadbee1"
    (c,) = commits.attribute([board_entry(1, "nils", "handoff", "status:070", None) | {"text": no_head}], "s", roster)
    assert c.commit == "deadbee"  # first SHA-shaped word with a digit; "base" ones and plain words are skipped


def test_build_cost_is_booked_on_the_features_last_commit_from_its_usage_rows(tmp_path):
    commits = load_commits()
    (tmp_path / "team").mkdir()
    (tmp_path / "team" / "dev-2.md").write_text("# Tomas\n\n- **name:** Tomas\n- **seat:** dev-2\n")
    sprint = tmp_path / "sprints" / "s1"
    sprint.mkdir(parents=True)
    sprint.joinpath("board.jsonl").write_text("\n".join(json.dumps(e) for e in [
        board_entry(1, "tomas", "handoff", "status:060", ["aaaaaaa"], "2026-11-05T12:00:00+00:00"),
        board_entry(2, "maren", "merge", "status:060", ["bbbbbbb"], "2026-11-05T13:00:00+00:00"),
        board_entry(3, "tomas", "handoff", "status:060-fix", ["ccccccc"], "2026-11-05T14:00:00+00:00"),
    ]) + "\n")
    # 060: (100000*5 + 10000000*0.1 + 400000*1.25) / 1e6 = 2 M units -> $8; the fix round $4.
    sprint.joinpath("usage.txt").write_text(
        "agent    calls  out  cacheRd  cacheWr  sends\n"
        "060 frontend build-runtime (Tomas)   10   100000   10000000   400000   0\n"
        "060 QA fix round (Tomas)   5   50000   5000000   200000   0\n"
        "059 runtime profiles (Nils)   5   50000   5000000   200000   0\n"
        "TOTAL {}\n")
    found = {c.commit: c for c in commits.collect(tmp_path, None)}
    assert found["aaaaaaa"].cost_usd is None
    assert found["bbbbbbb"].cost_usd == 8.0 and found["bbbbbbb"].seat == "tomas (dev-2)"
    assert found["ccccccc"].cost_usd == 4.0


def test_no_usage_file_means_no_cost_not_zero(tmp_path):
    commits = load_commits()
    sprint = tmp_path / "sprints" / "s1"
    sprint.mkdir(parents=True)
    sprint.joinpath("board.jsonl").write_text(json.dumps(board_entry(1, "tomas", "handoff", "status:060", ["aaaaaaa"])) + "\n")
    (c,) = commits.collect(tmp_path, None)
    assert c.cost_usd is None and c.seat == "tomas"  # no roster entry: the board name as is
    metrics = commits.payload([c])["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    assert [m["name"] for m in metrics] == ["build.commit.info"]
