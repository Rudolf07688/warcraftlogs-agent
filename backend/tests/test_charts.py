"""Chart spec validation + rendering (feature 005 / US2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.schemas import ChartSpec
from backend.app.services.charts import chart_spec_to_matplotlib, chart_spec_to_plotly
from wcl_agent.tools import create_chart


# --- create_chart tool validation ---------------------------------------------


def test_create_chart_success_normalizes_spec():
    r = create_chart("line", "DPS", '[{"name":"Raid","y":[1,2,3]}]', y_label="DPS")
    assert r["status"] == "success"
    chart = r["chart"]
    assert chart["kind"] == "line"
    assert chart["series"][0]["y"] == [1.0, 2.0, 3.0]
    assert chart["y_label"] == "DPS"


def test_create_chart_rejects_bad_kind():
    r = create_chart("pie", "T", '[{"name":"A","y":[1]}]')
    assert r["status"] == "error"
    assert "line" in r["valid"]


def test_create_chart_rejects_bad_json():
    r = create_chart("bar", "T", "{not json}")
    assert r["status"] == "error"


def test_create_chart_rejects_mismatched_x():
    r = create_chart("line", "T", '[{"name":"A","y":[1,2,3],"x":[0,1]}]')
    assert r["status"] == "error"


def test_create_chart_rejects_too_many_points():
    big = ",".join("1" for _ in range(600))
    r = create_chart("line", "T", f'[{{"name":"A","y":[{big}]}}]')
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
def test_chart_spec_to_matplotlib_each_kind(kind):
    spec = _spec().model_copy(update={"kind": kind})
    img = chart_spec_to_matplotlib(spec)
    assert img is not None


def test_chartspec_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        ChartSpec.model_validate({"kind": "donut", "title": "x", "series": [{"name": "a", "y": [1]}]})
