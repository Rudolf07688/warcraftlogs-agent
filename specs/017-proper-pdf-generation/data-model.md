# Data Model: Proper PDF Generation

There is **no database or Redis change**. Reports are still generated on demand and never stored. The only new types are in-process value objects passed from the API layer to the renderer (Principle IV: dataclasses for internal values).

## ReportDocument (dataclass, frozen)

This is the renderer's one input. The API layer builds it after the findings rewrite. It replaces the `messages`/`graphs`/`artifacts` dict lists that `render_report_pdf` takes today.

| Field | Type | Rules / source |
|---|---|---|
| `title` | `str` | Tracked-raid label, then conversation title, then `"WCL Report"`. The same chain as today, unchanged. Must not be empty. |
| `scope` | `Literal["conversation", "message"]` | Which endpoint was called. Shown in the title block as "Whole conversation" or "Single answer" (FR-008). |
| `generated_at` | `datetime` | Timezone-aware UTC. Shown as `YYYY-MM-DD HH:MM UTC`. |
| `body_markdown` | `str` | The findings Markdown from `report_synthesis.synthesize_findings`. Not empty, because the API already fails closed on empty output (FR-020). |
| `question` | `str \| None` | Single-answer scope only: the user message that prompted the answer, shown in the title block. Always `None` for the conversation scope. |
| `partial` | `bool` | Single-answer scope only: `True` when the source agent message has `status == "partial"`. When true, the document shows an "Interrupted — partial answer" note under the title block. Defaults to `False`. |
| `figures` | `tuple[ReportFigure, ...]` | In order: captured graphs first, then analyst charts (FR-012). May be empty, in which case the Charts section is left out. At most 20 (`api/reports._MAX_FIGURES`). |
| `figures_omitted` | `int` | How many figures the cap left out; when above 0 the Charts section ends with "N more charts not shown". Defaults to `0`. |

## ReportFigure (dataclass, frozen)

One chart in the Charts section.

| Field | Type | Rules / source |
|---|---|---|
| `title` | `str` | For a captured graph: `"{data_type} — {report_code}"`, the same as today's in-image title. For an analyst chart: `ChartSpec.title`. |
| `svg` | `bytes \| None` | Vector image from `charts.py`. `None` when the chart can't be drawn (malformed spec, no plottable series). The figure then shows the "Chart unavailable" note (FR-016). |
| `source_url` | `str` | `ChartSpec.source_url` for analyst charts. For captured graphs, the Warcraft Logs report URL built from `report_code` (and `fight_id` when present). The builder is `wcl_agent/benchmark.py::_fight_link`, promoted to a public `report_link(code, fight_id=None)` so the renderer and the benchmark tool share one URL format (Principle I). Empty string when unknown. Rendered as a link in the caption. |

The figure **number** isn't stored. The renderer assigns `Figure 1…N` by position, so numbers always match the order on the page.

### Building figures (API layer)

```text
captured graphs (repo.list_captured_graphs, filtered by message_seq for the message scope)
    → charts.graph_to_svg(graph_json, title)         → ReportFigure
analyst artifacts (repo.list_artifacts, same filter)
    → ChartSpec.model_validate(spec_json)
    → charts.chart_spec_to_svg(spec)                 → ReportFigure
    (validation or drawing error → svg=None, title from the spec if readable, else "Chart")
```

Scope filtering (`message_seq == seq` for single-answer reports, FR-021) stays exactly where it is today, in `api/reports.py`.

## Lifecycle

There are no states. `ReportDocument` is built per request, rendered off the event loop (`asyncio.to_thread`, FR-022), and thrown away. Any exception in building or rendering becomes the existing `500 pdf_generation_failed` with no file (FR-020).

## Removed types / shapes

- The `messages: list[dict]` input to the renderer. Both endpoints passed one synthetic agent message, which is now `body_markdown`.
- `graphs: list[dict]` and `artifacts: list[dict]` inputs. These are now `figures`.
- ReportLab `Image` as the return type of `charts.chart_spec_to_matplotlib`. The function is renamed `chart_spec_to_svg` and returns `bytes`; see the contract.
