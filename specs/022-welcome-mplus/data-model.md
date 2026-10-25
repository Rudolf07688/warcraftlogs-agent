# Data Model: 022

**recent_mplus_runs** (tenant-owned, RLS `tenant_id = current_setting('app.tenant_id')`)
- id uuid pk; tenant_id fk tenants (cascade); report_code varchar(32); fight_id smallint/int; dungeon varchar(120); key_level smallint (> 0); started_at timestamptz; timed boolean; first_seen_at timestamptz default now().
- Unique (tenant_id, report_code, fight_id). Index (tenant_id, started_at).

**recent_mplus_run_characters**
- run_id fk recent_mplus_runs (cascade), character_id fk user_characters (cascade), tenant_id fk; pk (run_id, character_id); index (tenant_id, character_id). Deleting a character removes the link, so runs only that character took part in stop showing (FR-011).

Value object: `MplusRun(fight_id, dungeon, key_level, started_at, timed)` in `recent_raid_types.py`.
Cache model: `FightSummary` gains optional `start_time_ms`, `keystone_level`, `keystone_bonus`, `keystone_time_ms`.
