# Data model: 046

No stored data changes.

## Compact table (tool result value of `table`)
- `_compact`: true
- `_truncated`: true only when some list omitted rows
- `_note`: says the top entries are present, which breakdowns were dropped, and to call again with `source_id` (or `fight_id`/`ability_id`) only for detail beyond them
- `data`: the table's scalar fields; each list of rows → top-N rows + `<list>_omitted`; a dict of lists walked one level
- Row: scalar fields of the WCL row minus `icon`; `class`, `spec` (from `icon` when it starts with `type`); `per_second`; nested `{name}` dicts → name

## Turn stats line
- adds `tool_calls=N`; `outcome` gains `empty`

## Search hit (tool result)
- `text`: `<data>` + neutralised text + `</data>`

## Kickoff pre-fetch job
- key `("kickoff_prefetch", tenant_id, report_code)`; ≤ 1 summary + 10 tables
