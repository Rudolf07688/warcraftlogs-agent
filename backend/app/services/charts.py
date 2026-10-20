"""Chart rendering (feature 005 / US2).

One ``ChartSpec`` (the agent's ``create_chart`` output, persisted as
``artifacts.spec_json``) is the single source of truth for two renderers:

* ``chart_spec_to_plotly`` → a Plotly figure ``{data, layout}`` for the interactive
  in-chat artifact and the reload path.
* ``chart_spec_to_svg`` → vector SVG so the same chart prints in the PDF export (no
  browser/kaleido dependency). ``graph_to_svg`` draws a captured WCL graph the same way.

Both bound the point/series counts defensively (the tool already caps them, but a
hand-crafted or legacy spec shouldn't be able to blow up rendering).
"""

from __future__ import annotations

import io
from itertools import cycle

from matplotlib.figure import Figure
from matplotlib.ticker import StrMethodFormatter

from ..schemas import ChartSpec

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


def figure_to_svg(fig: Figure, *, pad_inches: float = 0.1) -> bytes:
    """Serialize a matplotlib figure to SVG bytes.

    Callers build figures with the object-oriented ``Figure`` API, never pyplot, so
    concurrent report renders in worker threads share no global state.
    """
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=pad_inches, transparent=True)
    return buf.getvalue()


# PDF print style (FR-015/FR-017): every series differs by line style and marker (or
# hatch, for bars) as well as colour, so charts still read when printed in greyscale.
_COLORS = ("#4b2e1e", "#2b5d8a", "#b8862b", "#4f7a3a", "#8a2b4f", "#6b6b6b")
_LINES = (("-", "o"), ("--", "s"), (":", "^"), ("-.", "D"))
# Line patterns only: dot/circle hatches cost WeasyPrint ~300 ms and ~180 KB per chart.
_HATCHES = ("", "//", "\\\\", "xx", "--", "||")


def _styles():
    """Yield (colour, linestyle, marker, hatch) per series."""
    return zip(cycle(_COLORS), cycle(_LINES), cycle(_HATCHES))


def _new_axes():
    fig = Figure(figsize=(6.5, 3.2))
    ax = fig.subplots()
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(labelsize=8, colors="#444")
    return fig, ax


def _line(ax, name: str, xs: list, ys: list, style) -> None:
    color, (linestyle, marker), _hatch = style
    ax.plot(
        xs, ys, label=name, color=color, linestyle=linestyle, linewidth=1.4,
        marker=marker, markersize=3.5, markevery=max(1, len(ys) // 10),
    )  # fmt: skip


def _finish(fig: Figure, ax, *, x_label: str = "", y_label: str = "", n_series: int = 1) -> bytes:
    """Shared axes styling for every PDF chart. The title goes in the HTML caption."""
    if x_label:
        ax.set_xlabel(x_label, fontsize=9)
    if y_label:
        ax.set_ylabel(y_label, fontsize=9)
    if n_series > 1:
        ax.legend(fontsize="x-small", loc="best", frameon=False)
    if max(abs(v) for v in ax.get_ylim()) >= 10_000:
        ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))  # 1,234,567 DPS
    ax.grid(True, alpha=0.25, linewidth=0.6)
    fig.tight_layout()
    return figure_to_svg(fig)


def chart_spec_to_svg(spec: ChartSpec) -> bytes:
    """Render a ChartSpec to SVG for the PDF export."""
    fig, ax = _new_axes()
    bounded = _bounded(spec)
    if spec.kind == "bar":
        width = 0.8 / max(len(bounded), 1)
        for i, ((name, _xs, ys), (color, _line_style, hatch)) in enumerate(zip(bounded, _styles())):
            offsets = [p + i * width for p in range(len(ys))]
            ax.bar(offsets, ys, width=width, label=name, color=color, hatch=hatch, edgecolor="#ffffff")
        # Label the x ticks with the first series' x values when categorical.
        if bounded:
            _, xs0, ys0 = bounded[0]
            ax.set_xticks([p + (len(bounded) - 1) * width / 2 for p in range(len(ys0))])  # group centres
            ax.set_xticklabels([str(x) for x in xs0], fontsize="x-small", rotation=30, ha="right")
    else:
        for (name, xs, ys), style in zip(bounded, _styles()):
            color, (_linestyle, marker), _hatch = style
            if spec.kind == "scatter":
                ax.scatter(xs, ys, label=name, s=14, color=color, marker=marker)
            else:
                _line(ax, name, xs, ys, style)
                if spec.kind == "area":
                    ax.fill_between(xs if _numeric(xs) else range(len(ys)), ys, alpha=0.15, color=color)
    return _finish(fig, ax, x_label=spec.x_label, y_label=spec.y_label, n_series=len(bounded))


def _series_from_graph(graph_json: dict) -> list[tuple[str, list, list]]:
    """Best-effort extraction of (name, xs, ys) series from a WCL graph payload."""
    series_out: list[tuple[str, list, list]] = []
    data = graph_json.get("data") if isinstance(graph_json, dict) else None
    series = (data or {}).get("series") if isinstance(data, dict) else None
    if not isinstance(series, list):
        return series_out
    for i, s in enumerate(series[:_MAX_SERIES]):
        if not isinstance(s, dict):
            continue
        name = str(s.get("name") or f"series {i + 1}")
        points = s.get("data")
        xs: list = []
        ys: list = []
        if isinstance(points, list):
            for j, pt in enumerate(points[:_MAX_POINTS]):
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    xs.append(pt[0])
                    ys.append(pt[1])
                elif isinstance(pt, dict) and "y" in pt:
                    xs.append(pt.get("x", j))
                    ys.append(pt["y"])
                elif isinstance(pt, (int, float)):
                    xs.append(j)
                    ys.append(pt)
        if xs and ys:
            series_out.append((name, xs, ys))
    return series_out


def graph_to_svg(graph_json: dict) -> bytes | None:
    """Render a captured WCL graph payload to SVG, or None if nothing is plottable."""
    series = _series_from_graph(graph_json or {})
    if not series:
        return None
    fig, ax = _new_axes()
    for (name, xs, ys), style in zip(series, _styles()):
        _line(ax, name, xs, ys, style)
    return _finish(fig, ax, n_series=len(series))


def _numeric(xs: list) -> bool:
    return all(isinstance(x, (int, float)) for x in xs)
