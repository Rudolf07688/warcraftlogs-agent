# REST contract: recent M+ runs (022)

`GET /api/recent-raids` (extended, backward compatible): response adds
`mplus_runs: RecentMplusRun[]`, newest first, at most 6, empty when none. `raids` is now at most 6.

`RecentMplusRun`: `report_code: str`, `fight_id: int`, `dungeon: str`, `key_level: int`, `started_at: datetime`, `timed: bool`, `characters: {name, server, region}[]`.

`POST /api/recent-raids/mplus/{report_code}/{fight_id}/investigate` (session + CSRF), body `{model?: string|null}`.
- 201 `InvestigateResponse` `{conversation_id, model, kickoff_prompt}`; the conversation title is `M+ <dungeon> +<level>` (explicit).
- 404 `not_found` when the run is not one of the tenant's stored runs; 400 `invalid_model`.

Kickoff prompt (key phrases pinned in tests): names the report and fight; asks for the result against the timer (timed or depleted, by how much), the single biggest time loss per pull or boss segment, deaths (who, to what, avoidable), interrupt coverage, one headline improvement; stay at run and segment level, cast-level detail only where a segment clearly warrants it.
