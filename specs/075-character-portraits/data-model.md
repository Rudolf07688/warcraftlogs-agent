# Data model: 075

- **CharacterRef** (dataclass, internal): region, realm, name as stored.
- **PortraitCache** (Pydantic, Redis value under `ext:portrait:v1:<hash>`): `status: "found" | "none" | "unavailable"`, `url: str | None` (set only for found; re-validated on read).
- **PortraitOut** (API): `character_id: str`, `name`, `server`, `region`, `class_name: str | None`, `portrait_url: str | None`.
- **PortraitsOut** (API): `portraits: list[PortraitOut]`.
