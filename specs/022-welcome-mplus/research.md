# Research: 022

- **Run identity**: one keystone fight = (report code, fight id). Decision from clarify Q1.
- **Where keystone data comes from**: WCL v2 `ReportFight` exposes `keystoneLevel`, `keystoneBonus`, `keystoneTime`, `startTime`. Adding them to the shared `REPORT_SUMMARY_FIELDS` keeps one query (constitution I) and lets 020's write-through persist them with no client change.
- **Cache staleness**: summaries cached under `v1` lack keystone fields for up to 24 h. Bumping the key to `v2` is a one-line fix versus a day of silently empty M+ lists.
- **Timed vs depleted vs abandoned**: completed = `kill is True` with `keystoneLevel > 0`; timed = `keystoneBonus >= 1`; depleted = completed and not timed; abandoned = not completed, dropped. Decision from clarify Q2.
- **Storage**: new tables (see Complexity Tracking). Alternative of read-time derivation rejected (cache miss waits on WCL).
- **Cap settings**: separate display caps; `recent_raids_limit` stays the listing depth so M+ discovery from non-raid reports is not starved.
- **Scope of M+ report detail fetch**: newest 10 non-raid reports needing details per refresh, in the existing batches of 10; bounds WCL cost.
