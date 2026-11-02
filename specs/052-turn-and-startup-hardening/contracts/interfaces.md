# Contracts: Turn and startup hardening

## GET /api/admin/cache-stats (sc-332)

A new top-level field `store_by_operation`: `{ "<operation>": {hits, misses, not_visible,
timeouts, hit_rate} }` (the `store` shape), sorted by name. `<operation>` is one of the app's own
WCL operation names (`OWN_OPERATIONS` in `backend/app/services/raw_fetch_reads.py`) or `"custom"`
for any other query. `{}` when the cache is off or unavailable. Additive; `store` (the totals)
is unchanged.

## POST /api/raids/{code}/investigate (sc-352)

New `429 {"error": {"code": "rate_limited", "message": ..., "request_id": ...}}` with `Retry-After: 60` past `WCL_INVESTIGATE_PER_MINUTE`
(default 5) per user, checked before the 404 rule. Otherwise unchanged.

## Config (sc-352, sc-356)

- `WCL_INVESTIGATE_PER_MINUTE` (int, default 5).
- Startup refuses a weak `SECRET_KEY` (the dev default `dev-insecure-change-me`, empty or blank,
  under 32 characters, or containing `change-me`) unless `SITE_URL` is `http(s)` with no userinfo
  and its host is `localhost`, `127.0.0.1` or `::1`. It warns naming each insecure setting in
  use (`SECRET_KEY`, the built-in `DATABASE_URL`) without values.
