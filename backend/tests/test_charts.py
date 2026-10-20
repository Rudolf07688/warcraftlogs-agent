"""Chart spec validation + rendering (feature 005 / US2)."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from backend.app.schemas import ChartSpec
from backend.app.services.charts import (
    chart_spec_to_plotly,
    chart_spec_to_svg,
    graph_to_svg,
)
from wcl_agent.tools import create_chart

# --- create_chart tool validation ---------------------------------------------


async def test_create_chart_success_normalizes_spec():
    r = await create_chart("line", "DPS", '[{"name":"Raid","y":[1,2,3]}]', y_label="DPS")
    assert r["status"] == "success"
    chart = r["chart"]
    assert chart["kind"] == "line"
    assert chart["series"][0]["y"] == [1.0, 2.0, 3.0]
    assert chart["y_label"] == "DPS"


async def test_create_chart_rejects_bad_kind():
    r = await create_chart("pie", "T", '[{"name":"A","y":[1]}]')
    assert r["status"] == "error"
    assert "line" in r["valid"]


async def test_create_chart_rejects_bad_json():
    r = await create_chart("bar", "T", "{not json}")
    assert r["status"] == "error"


async def test_create_chart_rejects_mismatched_x():
    r = await create_chart("line", "T", '[{"name":"A","y":[1,2,3],"x":[0,1]}]')
    assert r["status"] == "error"


async def test_create_chart_rejects_too_many_points():
    big = ",".join("1" for _ in range(600))
    r = await create_chart("line", "T", f'[{{"name":"A","y":[{big}]}}]')
    assert r["status"] == "error"


# --- renderers ----------------------------------------------------------------


def _spec() -> ChartSpec:
    return ChartSpec.model_validate(
        {
            "kind": "line",
            "title": "Raid DPS",
            "x_label": "t",
            "y_label": "DPS",
            "series": [
                {"name": "Raid", "x": [0, 5, 10], "y": [100, 150, 120]},
                {"name": "Boss", "y": [90, 110, 80]},
            ],
        }
    )


def test_chart_spec_to_plotly_builds_traces():
    fig = chart_spec_to_plotly(_spec())
    assert len(fig["data"]) == 2
    assert fig["data"][0]["type"] == "scatter"
    assert fig["layout"]["title"]["text"] == "Raid DPS"
    # Series without x defaults to the point index.
    assert fig["data"][1]["x"] == [0, 1, 2]


@pytest.mark.parametrize("kind", ["line", "bar", "scatter", "area"])
def test_chart_spec_to_svg_each_kind(kind):
    spec = _spec().model_copy(update={"kind": kind})
    svg = chart_spec_to_svg(spec)
    assert b"<svg" in svg


def test_chartspec_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        ChartSpec.model_validate({"kind": "donut", "title": "x", "series": [{"name": "a", "y": [1]}]})


# --- PDF print style (feature 017 / US3) -------------------------------------------


def _series_spec(kind: str, n: int) -> ChartSpec:
    series = [{"name": f"S{i}", "y": [i + 1, i + 3, i + 2, i + 4]} for i in range(n)]
    return ChartSpec.model_validate({"kind": kind, "title": "T", "series": series})


def test_line_series_differ_without_colour():
    svg = chart_spec_to_svg(_series_spec("line", 3)).decode()
    dashes = set(re.findall(r"stroke-dasharray: ?([\d.,\s]+)", svg))
    assert len(dashes) >= 2  # solid + at least two distinct dash patterns (FR-017)


def test_bar_series_get_hatches():
    svg = chart_spec_to_svg(_series_spec("bar", 2)).decode()
    assert "<pattern" in svg  # hatch fill for the second series


def test_legend_only_with_several_series():
    assert b'id="legend_1"' not in chart_spec_to_svg(_series_spec("line", 1))
    assert b'id="legend_1"' in chart_spec_to_svg(_series_spec("line", 2))


def test_graph_to_svg_none_when_nothing_to_plot():
    assert graph_to_svg({}) is None
    assert graph_to_svg({"data": {"series": [{"name": "DPS", "data": []}]}}) is None
    svg = graph_to_svg({"data": {"series": [{"name": "DPS", "data": [[0, 1], [1, 2]]}]}})
    assert svg is not None and b"<svg" in svg


def test_hatches_are_line_patterns_only():
    # PERF-002: dot/circle hatches cost ~300 ms and ~180 KB per chart in WeasyPrint.
    from backend.app.services.charts import _HATCHES

    assert not set("".join(_HATCHES)) & set(".oO*")


def test_six_series_bar_chart_report_stays_small():
    from datetime import UTC, datetime

    from backend.app.services.pdf_report import ReportDocument, ReportFigure, render_report_pdf

    spec = _series_spec("bar", 6)
    doc = ReportDocument(
        title="T", scope="conversation", generated_at=datetime.now(UTC), body_markdown="x",
        figures=(ReportFigure("Bars", chart_spec_to_svg(spec)),),
    )
    assert len(render_report_pdf(doc)) < 60_000


def test_chart_text_and_bar_edges_suit_the_dark_page():
    from backend.app.services import report_theme as theme

    svg = chart_spec_to_svg(ChartSpec.model_validate(
        {"kind": "bar", "title": "DPS", "x_label": "Ability", "series": [
            {"name": "A", "x": ["a", "b"], "y": [1, 2]}, {"name": "B", "x": ["a", "b"], "y": [2, 3]}]}
    )).decode()
    assert theme.CREAM in svg and theme.OAK in svg
    assert "#ffffff" not in svg.lower() and "#444444" not in svg
