# Data model: 046

No stored data changes.

## Compact table (tool result value of `table`)
- `_compact`: true
- `_truncated`: true only when some list omitted rows, nested row lists included (048)
- `_note`: says the top entries are present, which breakdowns were dropped, and to call again with `source_id` (or `fight_id`/`ability_id`) only for detail beyond them
- `data`: the table's scalar fields; each list of rows → top-N rows + `<list>_omitted`; a dict of lists walked one level
- Row: scalar fields of the WCL row minus `icon`; `class`, `spec` (from `icon` when it starts with `type`); `per_second`; nested `{name}` dicts → name; nested row lists `entries`/`details` (Interrupts, Dispels) → their top-N rows + `<list>_omitted`, recursively (048); other nested lists (breakdowns) dropped

## Turn stats line
- adds `tool_calls=N`; `outcome` gains `empty`

## Closing no-answer token (stream record, 048)
- `{"type": "token", "text": <no-answer message>, "empty": true}`; the chat socket pops `empty` before sending (the wire frame stays `{type, text}`), saves the message, and skips the knowledge-base offer, the title job and follow-ups

## Search hit (tool result)
- `text`: `<data>` + neutralised text + `</data>`

## Kickoff pre-fetch job
- key `("kickoff_prefetch", tenant_id, report_code)`; ≤ 1 summary + 10 tables
- gate: `wcl_store_reads_enabled` and the store installed as the client's fetch source
- cooldown: `_started[(tenant_id, report_code)]` = monotonic start; a repeat within `COOLDOWN_S` (600 s) starts nothing; in-process, per app instance
- lanes: summary interactive (the turn's own first call, shared through the cache single-flight); boss tables in the background lane, promoted to interactive when a chat turn joins the flight (`LaneTicket`, `LaneLimiter.promote`)
