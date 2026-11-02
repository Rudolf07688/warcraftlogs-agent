# Data model: Report fights and kickoff

No stored data changes. Tool-result shapes only (see contracts/report-tools.md).

## LastKill (dict in `get_report_fights`)

| field | type | rule |
|---|---|---|
| fight_id | int | the boss kill with the latest start time (fight id breaks ties / missing times) |
| name | str | fight name, capped at 60 |
| encounterID | int | non-zero |
| difficulty | int or null | WCL difficulty id |
| difficulty_name | str or null | from `DIFFICULTY_NAMES` |

Null when the report has no boss kill. Boss fight = `encounter_id` non-zero and no keystone level.

## BossSummary (list entry in `get_report_fights.bosses`)

One per (encounterID, difficulty), in first-pull order.

| field | type |
|---|---|
| encounterID, name, difficulty, difficulty_name | as above |
| pulls, kills | int |
| last_kill_fight_id | int or null |
| last_pull_fight_id | int |

## Overview table (`get_report_table(overview=True).table`)

`{"_overview": true, "_truncated": bool, "_note": str, "data": {scalars..., <list>: top 10 rows,
<list>_omitted: int}}`; no `composition`, no nested dicts.
