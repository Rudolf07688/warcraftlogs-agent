# Agent Tools & Instruction Contract — feature 005

## New tool: `create_chart` (US2)

Added to `wcl_agent/tools.py` and to `agent.py` `TOOLS`. It declares a chart from data the agent
already has; it does **not** call WCL and has **no plotly dependency** (plotly runs on the backend).

```python
def create_chart(
    kind: str,            # "line" | "bar" | "scatter" | "area"
    title: str,
    series_json: str,     # JSON: [{"name": str, "x": [..]?, "y": [..]}, ...]  (x optional → index)
    x_label: str = "",
    y_label: str = "",
    source_url: str = "", # optional WCL link the chart is sourced from (US1)
) -> dict[str, Any]:
    """Render an interactive chart in the chat from data you have already gathered.

    Use this when a visualization aids the answer (DPS/HPS over time, spec comparison bars,
    ability breakdowns). Build `series_json` from numbers the WCL tools returned — never invent
    data. The chart appears inline in your reply; still explain it in text.

    Returns {"status":"success","chart": <ChartSpec>} or {"status":"error","error_message": ...}.
    """
```

**Validation (mirrors `run_wcl_graphql`'s `variables_json` handling)**
- `kind` ∈ {line, bar, scatter, area}, else error with the valid set.
- `series_json` parses to a non-empty list of `{name, y:[...], x?:[...]}`; `x` length (if present) ==
  `y` length; counts bounded (≤ 12 series, ≤ ~500 pts/series) else error asking to reduce.
- On success returns the normalized `ChartSpec` (see data-model.md) under `chart`.

The backend recognizes `name == "create_chart"` in `_handle_tool_end` and turns the returned `chart`
into a persisted `Artifact` + an `artifact` WS frame (see websocket.md). The tool result itself is small
(it is the spec), so it never trips the model-context size cap.

## INSTRUCTION additions (`agent.py`)

Append two short sections to the existing `INSTRUCTION` (keep the current WCL/domain/persona text):

**KNOWN PLAYER CONTEXT (US1)** — describes the preamble block the backend prepends each turn:
> You may be given a "KNOWN PLAYER CONTEXT" block listing the user's own character, their friends, and
> their main guild (with class/spec and short spec guides). When the question is about the user ("me/my/
> I"), their friends ("us/we"), or their guild, use those saved identities (and their guides) as the
> subject — you don't need the user to re-type names. When a question is clearly population-level or
> unrelated (e.g. "best spec overall", patch notes), answer normally and do NOT narrow it to the guild.

**CHARTS (US2)** — when to call `create_chart`:
> When a visualization makes the answer clearer (a trend over time, a spec/ability comparison), call
> `create_chart` with data you already fetched, then reference it in your text. Prefer a chart over a
> long table of raw time-series numbers. Pass `source_url` when the data came from a specific WCL view.

## Guide generation prompt (US6, internal — not a user-facing tool)

`services/guide.py` runs this over a disposable session on the **guide model** (web-search-capable
Gemini), reusing `stream_response` (as the greeting primer does):

> "Write a concise, current-retail World of Warcraft guide for **<class> <spec>**. Cover: core single-
> target rotation/priority, key secondary stats, and the standard talent/build choices. Keep it tight
> and practical (a few short sections). Use web search for current-patch accuracy and mention sources."

The collected text is persisted as the character's `guide_markdown`. For a **guild** lock-in, the task
instead compiles a brief recent-progression summary (zone/boss progress) and stores it as
`summary_markdown`.

## Caching note (US4)
`create_chart` is **not** cached (no WCL call). All WCL-backed tools are cached transparently at
`WCLClient.query` (see caching.md) — no per-tool changes needed.
