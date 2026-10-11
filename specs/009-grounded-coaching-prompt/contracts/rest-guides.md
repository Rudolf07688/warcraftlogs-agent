# Contract: Guides API & Class Guides UI — freshness (US5)

Extends feature 008's `/api/guides` (see `specs/008-profile-class-pages/contracts/guides-api.md`).
Endpoints, auth, CSRF, and rate limits are unchanged; only response models grow.

## Schemas (`backend/app/schemas.py`)

```python
GuideFreshness = Literal["current", "possibly_stale", "unknown"]

class GuideListItem(BaseModel):
    class_name: str
    class_display: str
    spec: str
    status: GuideStatus
    updated_at: datetime | None = None
    game_patch: str | None = None          # NEW
    generated_at: datetime | None = None   # NEW
    freshness: GuideFreshness | None = None  # NEW — None unless status == "ready"

class GuideOut(BaseModel):
    class_name: str
    spec: str
    status: GuideStatus
    guide_markdown: str | None = None      # guide-meta block already stripped
    updated_at: datetime | None = None
    game_patch: str | None = None          # NEW
    generated_at: datetime | None = None   # NEW
    freshness: GuideFreshness | None = None  # NEW
    sources: list[GuideSource] = []        # NEW — [{title, uri}]

class GuideSource(BaseModel):
    title: str | None = None
    uri: str
```

`freshness` is computed per request from `guide_freshness(game_patch, current_patch())`.
Pre-feature rows: `game_patch = null` ⇒ `freshness = "unknown"`.
`major_cooldowns` is **not** exposed over REST (internal coaching input; YAGNI).

## Generation (`backend/app/services/guide.py`)

- `_GUIDE_PROMPT` explicitly frames an **authoring** task (research R15): "You are
  writing a reference guide; general class knowledge is allowed; use web search for
  current-patch accuracy when available." It additionally asks for: the patch the
  guide targets, a "Major cooldowns" section with numeric cooldowns, and a final
  fenced block labelled `guide-meta` with JSON `{patch, major_cooldowns[...]}`
  (data-model §2), listing the spec's major throughput/defensive cooldowns with
  cooldown in seconds, charges, spell id when known, and `talent_modified`.
- `_generate_text(prompt, session_id=None)` returns `GeneratedText(text, sources,
  session_id)` — sources collected from the `grounding` records `stream_response`
  already emits; `session_id` reused when given. Guild summaries ignore sources.
- On success: strip the block, validate (`GuideMetaBlock`). **If missing/invalid,
  send one repair turn** on the same `session_id` ("Reply with only the `guide-meta`
  block for the guide above.") and parse that reply (research R10). Persist markdown
  + 4 new columns (metadata NULL if the repair also failed), then `set_guide_meta(...)`
  in the `wcl_agent` registry.
- Startup (lifespan): load all `ready` rows into the registry.

## Agent context (`backend/app/services/profile_context.py`)

Each injected spec guide heading gains its provenance, e.g.
`## Arthas — Frost (guide for patch 12.1 · current)` or
`(guide patch unknown · may be out of date)`. No other preamble change.

## UI (`frontend/src/components/profile/ClassGuidesTab.tsx`, `frontend/src/types.ts`)

- Types mirror the schema additions.
- List rows and the guide view show `Patch <game_patch>` (or "Patch unknown") and the
  generated date.
- `possibly_stale` / `unknown` ⇒ a visible "May be out of date" badge next to the
  existing Regenerate action (no new action).
- Guide view lists `sources` as links when present.
