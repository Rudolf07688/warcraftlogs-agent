# Contract: Guides REST API (feature 015)

Supersedes `specs/008-profile-class-pages/contracts/guides-api.md` and
`specs/009-grounded-coaching-prompt/contracts/rest-guides.md` for the endpoints below.
All endpoints require a session (`require_session`); mutations require CSRF
(`require_csrf`). Guides stay global (non-tenant DB session). The frontend is updated in the
same feature, so the old `/{class}/{spec}` paths are **replaced**, not aliased.

`content_type` path/query values: `raid` | `mplus`. Anything else → 422.
Unknown class/spec (not in the current roster, §roster) → 404 `{"code":"not_found"}`.

## Shared models (`backend/app/schemas.py`)

```python
ContentType = Literal["raid", "mplus"]
GuideStatus = Literal["none", "pending", "ready", "needs_review", "failed"]
GuideFreshness = Literal["current", "possibly_stale", "unknown"]
GuideDisplay = Literal["published", "draft", "none"]

class GuideSource(BaseModel):
    title: str | None = None
    uri: str
    tier: int | None = None          # 1..3 (tier-4 is never cited)
    date: date | None = None

class GuideSummary(BaseModel):       # one content type of one spec — list view
    content_type: ContentType
    status: GuideStatus              # latest run outcome ("none" = no row)
    has_published: bool
    refreshing: bool                 # pending AND has_published
    game_patch: str | None = None    # published version
    season: str | None = None        # published version (mplus)
    generated_at: datetime | None = None
    freshness: GuideFreshness | None = None   # None unless has_published

class GuideListItem(BaseModel):      # one row per spec (FR-028: each spec exactly once)
    class_name: str
    class_display: str
    spec: str
    role: Literal["tank", "healer", "dps"]
    raid: GuideSummary
    mplus: GuideSummary

class GuideListOut(BaseModel):
    guides: list[GuideListItem]      # full roster, ordered by class display then spec
    roster_source: Literal["game_data", "fallback"]

class GuideOut(GuideSummary):        # viewer — one content type
    class_name: str
    spec: str
    display: GuideDisplay            # what the viewer shows (data-model §2)
    guide_markdown: str | None = None      # published or (display=="draft") draft markdown
    sources: list[GuideSource] = []
    unconfirmed: list[str] = []            # areas left out (FR-005)
    review_issues: list[str] = []          # human-readable, only when display == "draft" (FR-049)
    failure_reason: str | None = None      # only when status == "failed"

class GuideGenerateIn(BaseModel):
    force: bool = False

class GuideReportIn(BaseModel):
    note: str = Field(min_length=5, max_length=500)

class GuideReportOut(BaseModel):
    id: uuid.UUID
    status: Literal["open", "fixed", "rejected"]
    created_at: datetime
```

The coaching brief is **not** exposed over REST (it is agent context). Its human-facing
part is the readable guide's "What the coach looks for" section (FR-017).

## Endpoints

### `GET /api/guides` → `GuideListOut`
Full roster × both content types, status columns only (PERF-014 pattern: no markdown/brief
loaded). Side effect: calls `maybe_scan_stale_guides()` (non-blocking, throttled; see
`guide-pipeline.md` §Staleness).

### `GET /api/guides/{class_name}/{spec}/{content_type}` → `GuideOut`
Side effects (non-blocking): stamps `last_wanted_at` (throttled to once per hour per row);
when the guide is stale and not pending, queues regeneration (FR-051 "on next open").
`display` rules: published if any; else draft (status `needs_review`) with
`review_issues`; else `none`.

### `POST /api/guides/{class_name}/{spec}/{content_type}/generate` (body `GuideGenerateIn`) → `GuideOut`
Rate-limited per user by the existing `guide_limiter` (one request per content type).
Semantics unchanged from 008 apart from the key: `pending` ⇒ no-op; `ready` & not stale &
not `force` ⇒ no-op; otherwise upsert `pending` and spawn generation. Never triggers the
other content type (FR-027). 429 body `{"code":"rate_limited", ...}` + `Retry-After`.

### `POST /api/guides/{class_name}/{spec}/{content_type}/reports` (body `GuideReportIn`) → `GuideReportOut` (201)
CSRF; per-user limit 5/min (429 as above); 404 when the guide has no published version.
Records `guide_generated_at` of the published version.

### `GET /api/admin/guide-reports?status=open` → `list[GuideReportAdminOut]`
`require_platform_admin`. `GuideReportAdminOut` = report fields + `class_name`, `spec`,
`content_type`, `outcome_note`, `resolved_at`, reporter `user_id` (no email).

## Characters (profile) contract change

`CharacterOut` replaces `guide_status` / `guide_updated_at` with:

```python
class CharacterGuides(BaseModel):
    raid: GuideStatus = "none"
    mplus: GuideStatus = "none"

class CharacterOut(BaseModel):
    ...
    guides: CharacterGuides          # derived from spec_guides for (class, active_spec, *)
```

`_char_out` / the profile list load both rows in one query (`get_spec_guides_for` keyed by
`(class, spec, content_type)`). Saving a character requests the `raid` guide; the `mplus`
guide too when the character has current-season Mythic+ rankings (FR-030).

## Status/label mapping (frontend)

| status (+flags) | Library badge | Characters indicator |
|---|---|---|
| none | — ("Not generated") | `M+ –` |
| pending, !has_published | "Generating…" (pending) | `M+ …` |
| pending, has_published | provenance + "Refreshing" (pending) | `M+ ✓` |
| ready | provenance (+ "May be out of date" when stale) | `M+ ✓` |
| needs_review, has_published | provenance + "Update held for review" (warn) | `M+ ✓` |
| needs_review, !has_published | "Unverified draft" (warn) | `M+ !` |
| failed, has_published | provenance + "Update failed" (warn) | `M+ ✓` |
| failed, !has_published | "Failed" (failed) | `M+ ×` |
