# Contract: Guides API — shared spec-guide library (US2)

New router `backend/app/api/guides.py`, registered in `main.py`. The library is **global**
(generic content), so these endpoints use the **non-tenant** DB dependency
(`db/session.get_session`) but still require authentication; mutations require CSRF and are
rate-limited. Prefix `/api/guides`.

## Schemas (`backend/app/schemas.py`)

```python
GuideStatus = Literal["none", "pending", "ready", "failed"]

class GuideListItem(BaseModel):
    class_name: str            # WCL filter value, e.g. "Paladin"
    class_display: str         # e.g. "Paladin" (from CLASS_SPECS["display"])
    spec: str                  # e.g. "Protection"
    status: GuideStatus
    updated_at: datetime | None = None

class GuideListOut(BaseModel):
    guides: list[GuideListItem]   # full roster (every class+spec), status-merged

class GuideOut(BaseModel):
    class_name: str
    spec: str
    status: GuideStatus
    guide_markdown: str | None = None   # present only when status == "ready"
    updated_at: datetime | None = None

class GuideGenerateIn(BaseModel):
    force: bool = False          # true = regenerate/refresh even if ready
```

## Endpoints

### `GET /api/guides` → `GuideListOut`
- Auth: `require_session`. Returns the **complete** class/spec roster (from `CLASS_SPECS`) left-merged with `spec_guides`; specs with no row report `status="none"` (SC-002). Ordered by class display then spec.

### `GET /api/guides/{class_name}/{spec}` → `GuideOut`
- Auth: `require_session`. `404 not_found` when `(class_name, spec)` is not in `CLASS_SPECS`. When no guide row exists → `status="none"`, `guide_markdown=null`.

### `POST /api/guides/{class_name}/{spec}/generate` → `GuideOut` (202-style; returns current state)
- Auth: `require_csrf`. Body `GuideGenerateIn`.
- `404 not_found` if `(class_name, spec)` not in `CLASS_SPECS`.
- **Rate-limited** per user (`guide_limiter.allow_request(str(user_id))`); over-limit ⇒ `429 {"code":"rate_limited","message":...}` + `Retry-After` (FR-014).
- Calls `ensure_spec_guide(class_name, spec, force=body.force)`:
  - already `ready` and not `force`, or already `pending` ⇒ no new generation (dedup; FR-013, SC-004); returns current `GuideOut`.
  - else ⇒ upsert `pending`, spawn off-loop generation (best-effort), return `GuideOut(status="pending")`.
- The frontend polls `GET /api/guides` (or the detail route) to observe `pending → ready|failed`.

## Acceptance mapping
- FR-006 spec-keyed; FR-007 shared/global (no tenant scoping; no user data); FR-008 full roster + status; FR-009 manual request any spec; FR-010 retry/refresh via `force`/failed re-request; FR-011 non-blocking (returns `pending`); FR-012 view content (`GuideOut.guide_markdown`); FR-013 dedup; FR-014 rate limit.
