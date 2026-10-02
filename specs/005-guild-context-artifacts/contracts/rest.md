# REST Contract — feature 005

New/changed HTTP endpoints. All bodies are Pydantic models (Principle IV). Existing endpoints
unchanged except where noted.

## Profile (US1)

### `GET /api/profile`
Returns the single global profile.

```jsonc
// 200 ProfileOut
{
  "self": {                           // CharacterOut | null
    "id": "…", "role": "self", "name": "Thrall", "server": "Stormrage", "region": "US",
    "class_name": "Shaman", "active_spec": "Enhancement",
    "guide_status": "ready", "guide_updated_at": "2026-10-02T12:00:00Z"
  },
  "friends": [ /* CharacterOut[] */ ],
  "guild": {                          // GuildOut | null
    "id": "…", "name": "Nighthold", "server": "Stormrage", "region": "US",
    "summary_status": "ready"
  }
}
```
`guide_markdown`/`summary_markdown` are **not** returned by default (kept server-side for context);
only status fields are exposed to the UI.

### `PUT /api/profile/self`  → `CharacterOut`
Body `CharacterIn { name, server, region }`. Upserts the single self row; sets `guide_status="pending"`
and schedules the background guide task (US6). Returns promptly (does not await the guide).

### `POST /api/profile/friends`  → `CharacterOut` (201)
Body `CharacterIn { name, server, region }`. Adds a friend; schedules the guide task.
409 if an identical `(name, server, region, role=friend)` already exists.

### `DELETE /api/profile/friends/{id}`  → 204
Removes a friend character.

### `PUT /api/profile/guild`  → `GuildOut`
Body `GuildIn { name, server, region }`. Replaces the single main guild (one-main-guild limit, FR-003);
sets `summary_status="pending"` and schedules the guild-summary task.

### `DELETE /api/profile/guild`  → 204
Clears the main guild.

**Schemas**
```python
class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    server: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=8)

class CharacterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    name: str; server: str; region: str
    class_name: str | None = None
    active_spec: str | None = None
    guide_status: str = "none"
    guide_updated_at: datetime | None = None

class GuildIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    server: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=8)

class GuildOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str; server: str; region: str
    summary_status: str = "none"

class ProfileOut(BaseModel):
    self: CharacterOut | None = None   # field name exposed as "self"
    friends: list[CharacterOut] = []
    guild: GuildOut | None = None
```

## Per-message PDF report (US5)

### `GET /api/conversations/{conv_id}/messages/{message_id}/report.pdf`
Renders a PDF scoped to one agent reply.
- Resolve `message_id` → the agent `Message` (404 if missing / not in `conv_id`).
- Include: the agent message + the nearest **preceding** user message (originating question) +
  `captured_graphs` and `artifacts` where `message_seq == message.seq`.
- Exclude all other messages (FR-023).
- Render via the existing `render_report_pdf` (reused), artifacts via `chart_spec_to_matplotlib`.
- 200 → `application/pdf`, `Content-Disposition: attachment; filename="wcl-message-<short>.pdf"`.
- 500 `pdf_generation_failed` on render error (never a corrupt file — FR-026).

The existing conversation-level `GET /api/conversations/{conv_id}/report.pdf` is unchanged (and also
gains artifact rendering).

## Conversation detail gains artifacts (US2/FR-011)

### `GET /api/conversations/{conv_id}` (existing) — response extended
`ConversationDetail` gains `artifacts: list[ArtifactOut]`, so reopening a conversation re-renders charts.

```python
class ArtifactOut(BaseModel):
    id: uuid.UUID
    message_seq: int | None = None
    kind: str
    title: str
    figure: dict            # {data, layout} — built from the stored ChartSpec on read
```
The frontend maps `artifacts` to messages by `message_seq`.
