# Contract: portraits

## GET /api/profile/portraits (session required)

200 `{"portraits": [{"character_id": "uuid", "name": "Thrall", "server": "Area 52", "region": "us", "class_name": "Shaman", "portrait_url": "https://render.worldofwarcraft.com/us/character/area-52/1/2-avatar.jpg" | null}]}`

- One entry per own and friend character of the caller's tenant, own first. Never reads names from the request.
- `portrait_url` is null when no portrait (not found, private, unsupported region, service down, not configured, still loading after the 4 s budget). When set it is `https://` on a Blizzard render host.
- 401 without a session.

## contract:class-avatar

`ClassAvatar({ char: { name, class_name, portrait_url? }, className? })`. Without `portrait_url` it renders the initials exactly as before; with one, the image loads lazily over the same box and the initials show until it loads or if it fails.
