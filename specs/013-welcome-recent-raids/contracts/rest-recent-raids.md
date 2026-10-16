# Contract: Recent Raids REST API

**Feature**: 013-welcome-recent-raids

All endpoints need a session (`require_session`), and the state-changing ones also need CSRF (`require_csrf`), following the existing routers. Every query is tenant-scoped through `get_tenant_db` with RLS (FR-017).

---

## `GET /api/recent-raids`

Returns the stored recent raids immediately (FR-010). It may also **start** a background refresh when one is due (FR-013), but it never waits for it to finish.

**Behaviour**:
1. Read the tenant's own characters, then compute `has_characters` and the current `character_set` hash.
2. If `has_characters`, try the atomic claim (data-model §3) with `force = false`. If the claim wins, **commit**, then schedule `run_recent_raid_refresh(tenant_id, run_id)` (research R5).
3. Return the stored raids and the refresh state. The state reflects the claim: it is `running` if this request just started a run.

**200 response** (`RecentRaidsResponse`):

```json
{
  "has_characters": true,
  "raids": [
    {
      "report_code": "aBcD1234efGH5678",
      "title": "Manaforge Omega - Heroic",
      "zone_name": "Manaforge Omega",
      "started_at": "2026-10-15T19:02:11Z",
      "difficulty": 4,
      "bosses_pulled": 8,
      "bosses_killed": 6,
      "is_final": true,
      "characters": [
        { "name": "Frostmage", "server": "Silvermoon", "region": "EU" },
        { "name": "Holyalt",   "server": "Silvermoon", "region": "EU" }
      ]
    }
  ],
  "refresh": { "status": "running", "last_success_at": "2026-10-15T23:40:00Z", "last_error": null }
}
```

**Rules**:
- `raids` holds at most **20** items, ordered by `started_at` descending. Only `is_raid = true` reports are included, and only those linked to at least one current own character (FR-004, FR-016).
- Each report appears once, with every linked own character listed in the order the characters were added (FR-006).
- `bosses_pulled` and `bosses_killed` are `null` until details are fetched. The UI then leaves out the kill count.
- With no own characters, the response is `has_characters: false`, `raids: []` and `refresh.status: "idle"`, and no claim is attempted (FR-007).
- `refresh.last_error` is one of `wcl_unavailable`, `rate_limited`, `timeout`, `unknown` or `null`. Exception text is never returned.

**Errors**: `401` without a session. There are no other errors: a failure to schedule a refresh is logged and the stored list is still returned.

---

## `POST /api/recent-raids/refresh`

An explicit **Retry** (FR-015). It needs CSRF.

**Behaviour**: claims with `force = true`. A forced claim only passes the 15-minute gate when the last status is `failed`, and it never takes over a run that is still live and not stale (FR-025).

**Responses**:
- `202` + `RecentRaidsRefreshOut` (`status: "running"`): the claim won and a refresh was scheduled.
- `200` + `RecentRaidsRefreshOut`: the claim did not win (already running, or not due). The body carries the current state.
- `409 {"detail": "no_characters"}`: the tenant has no own characters.

---

## `POST /api/raids/{report_code}/investigate`: extended

The request, response, kickoff wording and status codes are unchanged (`InvestigateRequest` → `201 InvestigateResponse`).

**Change**: when no tracked raid exists for `report_code` but a `recent_raids` row does for this tenant, the handler first upserts the tracked raid from it:
- `label = _build_label(...)` from `guild_name`, `zone_name` and `started_at`;
- plus zone, guild and `report_started_at`.

It then continues as today. After the call, the tracked raid shows up in `GET /api/raids` (FR-008, FR-009).

**Unchanged**: it returns `404 not_found` when the code is neither tracked nor a recent raid of this tenant. Arbitrary report codes still can't start an investigation.

---

## Frontend client (`frontend/src/api/restClient.ts`)

```ts
export async function getRecentRaids(): Promise<RecentRaidsResponse>;          // GET /api/recent-raids
export async function refreshRecentRaids(): Promise<RecentRaidsRefresh>;       // POST, csrf: true
// investigateRaid(reportCode, model) is reused unchanged
```

Types `RecentRaid`, `RecentRaidsRefresh` and `RecentRaidsResponse` are added to `frontend/src/types.ts`, mirroring the Pydantic models.

## Welcome panel states (FR-007)

| Condition | Shown |
|---|---|
| `has_characters = false` | Empty state: "Add your characters to see your recent raids", with a link to `/profile` |
| No raids, `refresh.status = "running"` | Skeleton cards (first load) |
| No raids, `refresh.status = "succeeded"` | Empty state: "No recent raids found for your characters" |
| No raids, `refresh.status = "failed"` | Alert "Couldn't load your raids" + **Retry** button |
| Raids present, `refresh.status = "failed"` | The list, plus a subtle "Couldn't refresh" note + Retry |
| Raids present, `refresh.status = "running"` | The list, plus a small "checking for new raids…" indicator. Polls every 3 s (research R6) |
