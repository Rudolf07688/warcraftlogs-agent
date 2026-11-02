# Contract: report tool changes (050)

## get_report_fights(report_code)

Added keys (computed from the full fight list, never capped):

```json
{
  "last_kill": {"fight_id": 32, "name": "Ula'tek", "encounterID": 3180, "difficulty": 4, "difficulty_name": "Heroic"},
  "bosses": [
    {"encounterID": 3180, "name": "Ula'tek", "difficulty": 4, "difficulty_name": "Heroic",
     "pulls": 3, "kills": 1, "last_kill_fight_id": 32, "last_pull_fight_id": 32}
  ]
}
```

- A fight entry carries `keystoneLevel` only when it is a Mythic+ key run.
- Uploader strings are capped: `title` 80 characters, `guild`, player names and fight names 60
  (cut with `…`).
- `fights` is still capped as before (`_preview` when over 60,000 characters).

## get_report_table(..., overview: bool = False)

- `overview=false`: unchanged shape (raw table, or the 046 compact projection).
- `overview=true`: `{"_overview": true, "_truncated": <rows omitted>, "_note": ..., "data": ...}`,
  each list cut to its top 10 rows by total, plain fields only, no `composition`, no nested
  dicts such as `playerDetails`. Same WCL query as `overview=false`.
- Every string in a returned table is capped at 60 characters.

## Instruction

- `<CONTEXT_RESOLUTION>` names `last_kill` for "last kill / last boss" questions.
- `<RECENT_RAID_KICKOFF>` appears only when the turn's user message starts with
  `RAID_KICKOFF_OPENING`; it asks for `overview=true` tables, one per boss from `bosses`.
