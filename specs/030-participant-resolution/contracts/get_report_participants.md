# Contract: get_report_participants

`get_report_participants(report_code: str, fight_id: int = 0) -> dict`

- `fight_id=0`: everyone who appeared in any fight of the report. M+: pass the keystone fight id for exactly that key's players.
- Success: rows as in data-model.md, sorted tank, healer, dps, then name; pets/NPCs excluded; provenance carries report code and fight id.
- Budget: row at most 120 chars; M+ result at most 1,500; 40-player raid at most 6,000; never `_truncated`.
- Errors (standard shape): request failure, unknown/inaccessible report, zero players.
- Registered in `wcl_agent` TOOL_GROUPS/TOOLS (not backend `extra_groups`); listed in `REPORT_SCOPED_TOOLS`.
- Filters are applied by the model on rows; no filter arguments.

Preamble contract: `Raids:` entries end with `(report <code>)`; `Recent M+ runs:` and `Recent raids:` lines as in the design, at most 5 each, newest first, about 600 chars; absent when nothing is stored.
