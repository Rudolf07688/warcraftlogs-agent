# Contract: Agent output — source links & PDF rendering

Two output-fidelity contracts: how the agent cites Warcraft Logs sources (US1) and what the
PDF export must render correctly (US3).

## Warcraft Logs source-link format (US1)

When an answer uses data retrieved from a Warcraft Logs tool, the agent MUST include a markdown
link to the corresponding WCL web page, built from identifiers already present in tool results:

```
https://www.warcraftlogs.com/reports/<report_code>
https://www.warcraftlogs.com/reports/<report_code>#fight=<fight_id>
https://www.warcraftlogs.com/reports/<report_code>#fight=<fight_id>&type=<metric>&source=<source_id>
```

Scoping rules:
- **Report-level** answer → link the report root.
- **Fight-specific** answer → add `#fight=<fight_id>`.
- **Player + metric** answer → add `&source=<source_id>&type=<metric>`, where `<metric>` ∈
  `damage-done` | `healing` | `damage-taken` | `casts` | `deaths` (map from the `data_type`/
  metric used).
- **Multiple sources** → one distinct link per source (FR-004); do not collapse.
- **Non-WCL content** (web search, general knowledge) → **no** WCL link (FR-005).

Markdown form: `[Report <code> — Ulgrax pull](https://www.warcraftlogs.com/reports/…#fight=12)`.

### Rendering (frontend)

`Markdown.tsx` renders links via `react-markdown`; add a custom `a` component that sets
`target="_blank"` and `rel="noopener noreferrer"` so links open in a new tab without losing
chat state (FR-003). No change to table/list rendering (already handled by `remark-gfm`).

## PDF rendering contract (US3)

`render_report_pdf` MUST render the following markdown constructs correctly (not as raw text):

| Construct | Required rendering |
|-----------|--------------------|
| GFM table (`\| a \| b \|` with a `---\|---` separator) | A laid-out `Table` with a header row; cell text wraps |
| Headings (`#`..`######`) | Styled heading (levels capped at 3) |
| Bulleted list (`-`/`*`), incl. a list with an intro line | Bulleted items |
| Numbered list (`1.`, `2.`, …) | Numbered items |
| Inline bold / italic / code | Bold / italic / monospace |
| Long unbroken token (report code, URL, ability name) | Wraps within page margins (no overflow) |
| Captured graphs | Rendered as images after the analysis (unchanged) |

Additional rules:
- A conversation with no captured graphs still produces an analysis-only PDF (unchanged).
- Partial/interrupted messages stay flagged inline (unchanged).
- User questions MAY be included as context headings before each answer (readability).
- On any rendering exception the endpoint returns `500 pdf_generation_failed` and never a
  corrupt/empty file (unchanged — FR-015).

### Verification artifact

A unit test feeds a message containing a table, headings, a bulleted list, a numbered list, a
long unbroken token, and a captured graph, and asserts `render_report_pdf` returns non-empty
`application/pdf` bytes (starts with `%PDF`) without raising.
