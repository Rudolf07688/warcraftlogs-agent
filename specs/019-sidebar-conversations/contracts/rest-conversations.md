# REST contract: conversations (feature 019 changes)

All routes stay under `/api/conversations` and are tenant-scoped through the
`__Host-session` cookie (`require_session` / `require_csrf`) and `get_tenant_db` (RLS
context). A foreign or unknown id is always `404 {"detail": "not_found"}`.

## `ConversationOut` (all list, create and get responses)

```json
{
  "id": "uuid",
  "title": "string",
  "model": "string",
  "created_at": "2026-10-25T10:00:00Z",
  "updated_at": "2026-10-25T10:05:00Z",
  "pinned_at": "2026-10-25T10:06:00Z"
}
```

`pinned_at` is new. It is `null` when the conversation is not pinned. The field is
additive, so existing clients ignore it.

`GET /api/conversations` keeps its order (`updated_at` desc). The client builds the
Pinned group from `pinned_at`, ordering it by `pinned_at` desc.

## `PATCH /api/conversations/{conv_id}` (new)

- **Auth**: a session cookie plus the `x-csrf-token` header, with a matching `Origin`
  (`require_csrf`, the same as `DELETE`).
- **Body** (`ConversationUpdate`, extra keys rejected):

```json
{ "pinned": true }
```

- **200**: the updated `ConversationOut`.
  - `pinned: true` sets `pinned_at` to now, or keeps the existing value if the
    conversation is already pinned.
  - `pinned: false` sets `pinned_at` to `null`.
  - `updated_at` is unchanged in both cases.
- **404** `{"detail": "not_found"}`: the id belongs to another tenant or doesn't exist.
  No row changes.
- **401/403**: no session, or a missing or wrong CSRF token or Origin (existing
  behaviour of `require_csrf`).
- **422**: the body is missing `pinned`, `pinned` is not a boolean, or the body has
  unknown keys.

## Unchanged

`POST /api/conversations` keeps its body. Passing `title` now also marks the conversation
as explicitly named (it is never auto-renamed). `POST /api/raids/{code}/investigate`
creates the conversation with the raid label, so it is explicitly named too.
`GET /api/conversations/{id}` and `DELETE /api/conversations/{id}` are unchanged, apart
from `pinned_at` appearing in the GET body.
