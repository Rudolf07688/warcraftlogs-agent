# Agent tools (sc-131, ToolGroup "Stored data")

| Tool | Args | Success |
|---|---|---|
| `list_stored_fights` | `report_code` | `{"status":"success","report_code","title","fights":[{id,name,encounter_id,difficulty,kill,start_time_ms,size}] (≤100), "truncated"}` |
| `get_stored_fight_table` | `report_code, data_type, fight_id=0, source_id=0, ability_id=0, hostility_type="Friendlies"` | `{"status":"success","data_type","table"}` (capped like `get_report_table`) |
| `list_stored_reports_for_character` | `name, realm, region` | `{"status":"success","character","reports":[{code,title,start_time_ms,zone}] (≤25)}` |

Absent, invisible or stale → `{"status":"not_stored","message":"Not stored locally; use the WCL report tools."}` (identical).
Resolver error → its correctable error dict. Outside an authenticated turn → `{"status":"error",...}` (fail closed).
