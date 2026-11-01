# Data model: Knowledge base search (044)

044 adds no table and no migration. It reads 043's chunk tables (0019, schema on the board
#36) and the existing `user_characters`, `known_players`, `known_encounters`. All types below
are in-process value objects (dataclasses) except the tool result, which crosses the
agent boundary as a plain dict built from them.

## Read: 043's chunk tables (columns 044 uses)

| Table | Columns read | Notes |
|---|---|---|
| `kb_chunks` (global) | `id`, `kind` (`wcl`/`guide`), `raw_fetch_id` (= `raw_fetches.query_key`), `guide_id`, `label`, `text`, `embedding` (NULL = pending), `tsv`, `report_code`, `encounter_id`, `difficulty`, `fight_id`, `start_time`, `players` jsonb `[{name, key, class, spec}]`, `class_name`, `spec`, `content_type`, `section` | wcl rows visible only through `fetch_visible_clause(raw_fetch_id, …)` |
| `kb_chat_chunks` (tenant, RLS) | `id`, `tenant_id`, `conversation_id`, `message_seq`, `created_at`, `characters` jsonb `[{name, key}]`, `label`, `text`, `embedding`, `tsv` | session scoped with `set_scope`; plus `tenant_id = :tenant` |

`players[].key` and `characters[].key` are `name_key(name)` from the resolver (one definition).

## Resolver (sc-304) — `backend/app/services/name_resolver.py`

| Type | Fields | Rules |
|---|---|---|
| `ClassSpec` | `class_name: str`, `spec: str \| None`, `role: str \| None` | canonical roster filter values; role from `role_for_spec` |
| `ResolvedEncounter` | `id: int`, `name: str`, `zone_id: int \| None`, `zone_name: str \| None` | from the zone list or `known_encounters` |
| `ResolvedDifficulty` | `id: int`, `name: str` | 1 LFR, 3 Normal, 4 Heroic, 5 Mythic, 10 Mythic+ |
| `ResolvedCharacter` | `name`, `server`, `region`, `class_name \| None`, `spec \| None`, `key` | `key = name_key(name)`; own, friend or known player of the caller's workspace |
| `ResolutionError(ValueError)` | `field: str`, `value: str`, `reason: Literal["unknown","ambiguous"]`, `matches: tuple[str, ...]` (≤ 5) | `str(err)` is the correctable message for the agent |

## Search (sc-114) — `backend/app/kb/search.py`

| Type | Fields | Rules |
|---|---|---|
| `SearchFilters` | `kind: Kind \| None`, `report_code: str \| None`, `pairs: tuple[ClassSpec, ...]` (spec filter), `class_name: str \| None`, `encounter_id: int \| None`, `difficulty: int \| None`, `character_key: str \| None`, `since`, `until: datetime \| None` | built only from resolved values; frozen; `without(name)` returns a copy with one soft filter removed |
| `SearchRequest` | `queries: tuple[str, ...]` (1–5), `filters: SearchFilters`, `hard: frozenset[str]`, `k: int` (1–15), `tenant_id: UUID` | `hard` = `user_stated` ∩ soft filter names; `kind`/`report_code`/`difficulty`/`character` are always hard |
| `Candidate` | `chunk_id`, `kind`, `source_key: tuple`, `source: dict`, `text`, `leg: Literal["vector","keyword"]`, `rank: int` | one row of a leg; `source_key` per R8 |
| `Hit` | `kind`, `source: dict`, `text` (≤ 400 chars), `score: float`, `relaxed: bool` | `relaxed` only serialised when true |
| `SearchResult` | `hits: list[Hit]`, `mode: Literal["hybrid","keyword_only"]`, `relaxed: list[str]`, `capped: bool`, `note: str \| None` | serialised ≤ 6,000 chars |

### Relaxation state

```
pass 0: all filters
pass i: previous filters minus the next present, not-hard soft filter in
        [spec, class, encounter, dates]
stop:   len(deduped hits) >= k, or no droppable filter left
merge:  hits of pass 0, then new sources of pass 1 (relaxed=True), …; truncate to k
```

### Source pointer (what the agent sees)

| kind | `source` |
|---|---|
| wcl | `{report_code, fight_id, label}` |
| guide | `{class_name, spec, content_type, section}` |
| chat | `{conversation_id, message_seq}` |

## Eval (sc-115) — `backend/evals/kb/`

| File | Shape |
|---|---|
| `corpus.json` | `{"wcl": [...], "guide": [...], "chat": [...]}`: each chunk `{id, text, label, …filter columns}`; wcl chunks name a fixture report code and fight |
| `questions.json` | `[{id, question, expected: [chunk id], filters: {kind?, class_name?, spec?, encounter?, difficulty?, report_code?, character?}}]`, about 30 |
| `embeddings.json` (optional, written by `record`) | `{"set": "vertex:<model>", "dim": 768, "vectors": {"<chunk or question id>": [floats]}}` |
| report (stdout / JSON) | `{set, k, modes: {hybrid: {recall, p50_ms, p95_ms}, vector: {…}, keyword: {…}}}` |
