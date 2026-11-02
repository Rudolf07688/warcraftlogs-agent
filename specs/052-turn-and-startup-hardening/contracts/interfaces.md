# Contracts: Turn and startup hardening

## GET /api/admin/cache-stats (sc-332)

`store` gains `by_operation`: `{ "<WCL operation name>": {hits, misses, not_visible, timeouts, hit_rate} }`.
Additive; totals unchanged.

## POST /api/raids/{code}/investigate (sc-352)

New `429 {"code": "rate_limited", ...}` with `Retry-After: 60` past `WCL_INVESTIGATE_PER_MINUTE`
(default 5) per user, checked before the 404 rule. Otherwise unchanged.

## Config (sc-352, sc-356)

- `WCL_INVESTIGATE_PER_MINUTE` (int, default 5).
- Startup refuses `SECRET_KEY=dev-insecure-change-me` when `SITE_URL`'s host is not
  `localhost`, `127.0.0.1` or `::1`; it warns naming each insecure default in use
  (`SECRET_KEY`, `DATABASE_URL`) without values.
