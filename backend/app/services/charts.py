"""Chart rendering (feature 005 / US2).

One ``ChartSpec`` (the agent's ``create_chart`` output, persisted as
``artifacts.spec_json``) is the single source of truth for two renderers:

* ``chart_spec_to_plotly`` → a Plotly figure ``{data, layout}`` for the interactive
  in-chat artifact and the reload path.
* ``chart_spec_to_matplotlib`` → a ReportLab ``Image`` so the same chart prints in
  the PDF export (no browser/kaleido dependency).

Both bound the point/series counts defensively (the tool already caps them, but a
hand-crafted or legacy spec shouldn't be able to blow up rendering).
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")  # headless backend — no display needed
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import Image  # noqa: E402

from ..schemas import ChartSpec  # noqa: E402

_MAX_SERIES = 12
_MAX_POINTS = 500


def _bounded(spec: ChartSpec) -> list[tuple[str, list, list[float]]]:
    """Return [(name, xs, ys)] with x defaulted to the index, counts clamped."""
    out: list[tuple[str, list, list[float]]] = []
    for s in spec.series[:_MAX_SERIES]:
        ys = list(s.y[:_MAX_POINTS])
        xs = list(s.x[:_MAX_POINTS]) if s.x is not None else list(range(len(ys)))
        out.append((s.name, xs, ys))
    return out


def chart_spec_to_plotly(spec: ChartSpec) -> dict:
    """Build a Plotly figure ``{data, layout}`` from a ChartSpec."""
    data: list[dict] = []
    for name, xs, ys in _bounded(spec):
        if spec.kind == "bar":
            trace = {"type": "bar", "name": name, "x": xs, "y": ys}
        elif spec.kind == "scatter":
            trace = {"type": "scatter", "mode": "markers", "name": name, "x": xs, "y": ys}
        elif spec.kind == "area":
            trace = {
                "type": "scatter",
                "mode": "lines",
                "fill": "tozeroy",
                "name": name,
                "x": xs,
                "y": ys,
            }
        else:  # "line"
            trace = {"type": "scatter", "mode": "lines", "name": name, "x": xs, "y": ys}
        data.append(trace)

    layout = {
        "title": {"text": spec.title},
        "xaxis": {"title": {"text": spec.x_label}} if spec.x_label else {},
        "yaxis": {"title": {"text": spec.y_label}} if spec.y_label else {},
        "margin": {"l": 50, "r": 20, "t": 50, "b": 40},
        "legend": {"orientation": "h"},
    }
    return {"data": data, "layout": layout}


def chart_spec_to_matplotlib(spec: ChartSpec) -> Image:
    """Render a ChartSpec to a ReportLab ``Image`` for the PDF export."""
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    try:
        bounded = _bounded(spec)
        if spec.kind == "bar":
            n = len(bounded)
            for i, (name, xs, ys) in enumerate(bounded):
                positions = range(len(ys))
                width = 0.8 / max(n, 1)
                offsets = [p + i * width for p in positions]
                ax.bar(offsets, ys, width=width, label=name)
            # Label the x ticks with the first series' x values when categorical.
            if bounded:
                _, xs0, ys0 = bounded[0]
                ax.set_xticks(range(len(ys0)))
                ax.set_xticklabels([str(x) for x in xs0], fontsize="x-small", rotation=30, ha="right")
        else:
            for name, xs, ys in bounded:
                if spec.kind == "scatter":
                    ax.scatter(xs, ys, label=name, s=12)
                elif spec.kind == "area":
                    ax.plot(xs, ys, label=name)
                    ax.fill_between(range(len(ys)) if not _numeric(xs) else xs, ys, alpha=0.25)
                else:  # line
                    ax.plot(xs, ys, label=name)

        ax.set_title(spec.title)
        if spec.x_label:
            ax.set_xlabel(spec.x_label)
        if spec.y_label:
            ax.set_ylabel(spec.y_label)
        ax.legend(fontsize="x-small", loc="best")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=130)
        buf.seek(0)
    finally:
        plt.close(fig)
    return Image(buf, width=6.5 * inch, height=3.2 * inch)


def _numeric(xs: list) -> bool:
    return all(isinstance(x, (int, float)) for x in xs)
