# Data Model: Grounded, Patch-Aware Class Guides

Feature 015. Persistent changes are one Alembic migration (`0011_guide_content_types`) on the
global `spec_guides` table plus one new global table. Everything else is a typed in-process
model (Pydantic at boundaries, dataclasses inside — Constitution IV) or a Redis cache
family reusing feature 014's `get_or_load`.

## 1. Content type

```python
ContentType = Literal["raid", "mplus"]   # API / DB value; UI labels "Raid" / "Mythic+"
```

Every guide, brief, data sheet, fact, inaccuracy report and accuracy test case carries
exactly one content type (spec Key Entities). `"raid"` is the default everywhere a single
value is needed (FR-011 fallback, migration backfill, UI switch default).

## 2. `spec_guides` (existing table, extended) — migration 0011

Global, no tenant, no RLS (unchanged rationale from feature 008). Identity changes from
`(class_name, spec)` to `(class_name, spec, content_type)`.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | no | unchanged |
| class_name | varchar(40) | no | WCL PascalCase, from the roster (§6) |
| spec | varchar(40) | no | WCL PascalCase |
| **content_type** | varchar(8) | no | `raid` \| `mplus`; server default `raid` backfills existing rows (FR-055) |
| status | varchar(14) | no | widened from 10: `pending` \| `ready` \| `needs_review` \| `failed` (absent row ⇒ `none`) — the **latest generation run's** outcome |
| guide_markdown | text | yes | **published** readable guide (last version that passed review) |
| **brief** | JSONB | yes | **published** `CoachingBrief` (§4.6) |
| **claims** | JSONB | yes | **published** `list[GuideClaim]` both renderings came from |
| game_patch | varchar(20) | yes | published version's patch (existing) |
| **season** | varchar(40) | yes | published version's Mythic+ season name (mplus only) |
| generated_at | timestamptz | yes | published version's generation time (existing) |
| sources | JSONB | yes | published `[{title, uri, tier, date}]` (existing column, richer items) |
| major_cooldowns | JSONB | yes | published cooldowns (existing; now derived from `brief.cooldowns`, kept for the registry/back-compat) |
| **briefing** | JSONB | yes | the `GenerationBriefing` the published version was generated under |
| **evidence** | JSONB | yes | published `EvidenceSnapshot` (data sheet + fact sheet ids/values claims reference) — audit + accuracy check |
| **draft** | JSONB | yes | latest unpublished run output when `status = needs_review`: `{brief, claims, markdown, briefing, generated_at}` |
| **review_issues** | JSONB | yes | open `list[ReviewIssue]` for the latest run (needs_review) or check failures (failed) |
| **failure_reason** | varchar(200) | yes | short machine-readable reason for `failed` (e.g. `patch_unknown`, `check:patch_mismatch`, `model_error`) |
| **stale_reason** | varchar(40) | yes | `patch_changed` \| `season_changed` \| `hotfix` \| `legacy` \| NULL — set by the stale scan (FR-050), cleared on publish |
| **last_wanted_at** | timestamptz | yes | last time the guide was opened, its spec was resolved for a saved character, or its brief was given to the agent (in-use rule, FR-051) |
| created_at / updated_at | timestamptz | no | unchanged |

Constraints / indexes:
- drop `uq_spec_guide_identity (class_name, spec)`; add
  `uq_spec_guide_identity (class_name, spec, content_type)`.
- `ix_spec_guides_stale (stale_reason) WHERE stale_reason IS NOT NULL` is **not** added
  (≤ ~80 rows; a scan is cheaper than an index — YAGNI).

Migration backfill (FR-055): existing rows get `content_type='raid'`,
`stale_reason='legacy'`; their markdown/cooldowns stay published so nothing disappears, and
the in-use rule regenerates them through the new pipeline.

### Published vs. latest run (FR-037, FR-049, FR-053)

The row holds **one published version** (columns marked "published") and the **latest run
status**. Publishing overwrites the published columns atomically and clears
`draft`, `review_issues`, `failure_reason` and `stale_reason`. Any other run outcome leaves
the published columns untouched.

Derived read-time fields (never stored):

| Field | Rule |
|---|---|
| `has_published` | `brief IS NOT NULL OR guide_markdown IS NOT NULL` |
| `display` | `published` if `has_published`; else `draft` if `status = needs_review`; else `none` |
| `refreshing` | `status = pending AND has_published` |
| `freshness` | `current` \| `possibly_stale` \| `unknown` — from `stale_reason`, `game_patch` vs live patch (`guide_freshness`, unchanged), and for mplus `season` vs live season |
| `agent_brief` | the published `brief` only — never `draft` (FR-016, FR-049) |

### State transitions (per row)

```text
(no row) ──generate──▶ pending
pending ──checks+review pass──▶ ready            (publish; clears stale_reason, draft, issues)
pending ──review rounds exhausted──▶ needs_review (draft + review_issues; published untouched)
pending ──patch unknown / model error / check failure after repair──▶ failed (failure_reason; published untouched)
ready | needs_review | failed ──generate(force) or stale-regeneration──▶ pending
ready ──stale scan──▶ ready + stale_reason set     (status unchanged; freshness = possibly_stale)
```

Dedup is unchanged: `pending` ⇒ no new run; `ready` and not stale and not `force` ⇒ no-op.
A stale `ready` row regenerates when in use (FR-051) or when next opened/requested.

## 3. `guide_inaccuracy_reports` (new table) — migration 0011

Global (follows `spec_guides`; see plan Complexity Tracking): the generator runs outside any
tenant scope and must read open reports for a guide; the maintainer reads them through a
platform-admin endpoint. Holds no profile data — a guide key, a short note and the reporter.

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | no | pk |
| class_name / spec / content_type | varchar | no | the guide reported (FK-less: a report survives regeneration) |
| user_id | uuid | no | reporter (FK `users.id` ON DELETE CASCADE) |
| note | varchar(500) | no | trimmed, 5–500 chars |
| guide_generated_at | timestamptz | yes | which published version was reported |
| status | varchar(12) | no | `open` \| `fixed` \| `rejected` |
| outcome_note | varchar(300) | yes | reviewer's one-line reason (FR-052) |
| resolved_at | timestamptz | yes | set by the regeneration that judged it |
| created_at | timestamptz | no | |

Index `ix_guide_reports_open (class_name, spec, content_type) WHERE status = 'open'`.
Per-user rate limit: reuses `InProcessRateLimiter` (new instance, 5/min).

## 4. Pipeline models (`backend/app/services/guide_pipeline/models.py`, Pydantic v2)

All are Pydantic because they cross the model boundary (structured LLM output is
externally-sourced data that must be validated — Constitution IV) and are persisted as JSON.

### 4.1 `GenerationBriefing` (FR-002)

| Field | Type | Notes |
|---|---|---|
| now_utc | datetime | computed per run |
| content_type | ContentType | |
| class_name, class_display, spec, role | str | from the roster |
| class_specs | list[str] | full spec list of the class |
| live_patch | str | `12.1.5` from the version source (research R1), else WCL partition major.minor; generation postponed when neither is known (FR-006) |
| live_build | str \| None | `VersionsName`, e.g. `12.1.5.70448` (FR-007) |
| latest_hotfix_at | datetime \| None | newest Blizzard "Hotfixes:" article `dateModified` (research R2) |
| hotfix_touches_spec | bool | the latest hotfix lists this class (no spec sub-heading) or this spec |
| raid_tier | str \| None | current raid zone name |
| mplus_season | str \| None | current Mythic+ zone/season name |
| product / environment / region | Literal["retail"] / Literal["live"] / str | region = "US" default for evidence lookups |

### 4.2 `DataSheet` (FR-032..FR-035)

| Field | Type | Notes |
|---|---|---|
| class_name, spec, content_type | | |
| scope | `SampleScope` | zone id/name, partition, difficulty (raid) or key-level floor (mplus), encounters, metric, `sample_size`, collected_at |
| sufficient | bool | `sample_size >= MIN_SAMPLE` (research R6) |
| abilities | list[`ObservedAbility`] | `{ability_id, name, casts_per_min_median, casts_per_min_p25, casts_per_min_p75, min_gap_s, players_using}` |
| uptimes | list[`ObservedUptime`] | `{ability_id, name, kind: buff\|debuff, uptime_pct_median, players}` |
| talent_builds | list[`ObservedBuild`] | from ranking entries' `talents[{talentID, points}]` (research R5): `{talent_ids_hash, share_pct, players, notable_talents: list[{talent_id, name \| None}]}`; names only when the optional talent-name source is enabled |
| talent_pick_rates | list[{talent_id, name \| None, pick_pct}] | per-talent share among ranking entries (for "most top players take X") |
| stat_spread | list[`ObservedStat`] | `{stat, median_rating, p25, p75}` from `playerDetails.combatantInfo.stats` (≤10 players) |
| item_level_median | float \| None | from ranking `gear` |

Every fact id used in claims is `ds:<kind>:<ability_id|stat|build_hash>`.

### 4.3 `EvidenceItem` / `FactSheet` (FR-039..FR-044)

`EvidenceItem`: `id` (`src:<n>`), `statement` (paraphrased fact, ≤300 chars), `topic`
(`rotation|cooldowns|talents|stats|mechanics|affixes|other`), `source_url`, `source_title`,
`source_date` (date \| None), `tier` (1..4), `product`, `environment`, `patch` (str \| None),
`content_type` (ContentType \| `both`), `superseded` (bool).

`FactSheet`: `items: list[EvidenceItem]` (after hard filters), `dropped: list[{url, reason}]`
(for audit and the leakage metric), `conflicts: list[{topic, item_ids}]`.

Hard filter (code, not model) drops: wrong product/environment (PTR/beta/Classic URL or
title markers), `patch` older than live major.minor, wrong class/spec/content type,
`source_date` before `latest_hotfix_at` for the spec (unless flagged), tier 4 as sole
support (kept for discovery, never citable).

### 4.4 `EvidenceSnapshot`

`{data_sheet: DataSheet | None, fact_sheet: FactSheet}` — persisted on publish (`evidence`).

### 4.5 `GuideClaim` (FR-038, FR-045..FR-047)

| Field | Type | Notes |
|---|---|---|
| id | str | `c<n>` |
| section | Literal | `priority`, `cooldowns`, `uptimes`, `talents`, `stats`, `mistakes`, `benchmarks`, `content_notes` (boss mechanics / affixes), `overview` |
| text | str ≤ 300 | one statement, in our own words (FR-043) |
| evidence_type | Literal["observed","benchmarked","guidance"] | |
| evidence_refs | list[str] ≥ 1 | `ds:*` or `src:*` ids (FR-036 "evidence reference on every claim") |
| log_check | `LogCheck \| None` | required for `mistakes`, `uptimes`, `cooldowns`, `benchmarks` (FR-009) — `{signal: casts\|uptime\|cooldown_usage\|deaths\|damage_taken\|other, ability_id: int \| None, expectation: str ≤ 160}` |
| confidence | Literal["high","medium","low"] | low when data insufficient or single tier-3 source |
| verdict | Literal["confirmed","contradicted","unconfirmed"] \| None | set by review |

### 4.6 `CoachingBrief` (FR-008..FR-017) — the agent-facing output

Built **by code** from confirmed claims (never free-written by the model), so its structure
and size are guaranteed.

| Field | Type |
|---|---|
| class_name, spec, content_type, role | str |
| patch / season | str / str \| None |
| generated_at | datetime |
| priority | list[BriefItem] (ordered) |
| cooldowns | list[BriefCooldown] — `{name, ability_id: int \| None (data sheet only, FR-034), cooldown_s, charges, usage: str, log_check, evidence_type, confidence}` |
| uptimes | list[BriefItem] |
| talents / stats | list[BriefItem] (observed, with scope) |
| mistakes | list[BriefItem] (each with `log_check`) |
| benchmarks | list[BriefItem] (cpm/uptime numbers with sample scope) |
| content_notes | list[BriefItem] (raid mechanics or M+ affix/route play) |
| unconfirmed | list[str] — areas left out (FR-005) |
| data_sufficient | bool |

`BriefItem` = `{text, evidence_type, confidence, log_check | None, claim_id}`.

Rendering (`render_brief_text`) produces the compact text the agent sees (contract
`contracts/coaching-brief.md`); `len(render_brief_text(b)) <= BRIEF_MAX_CHARS` is an
automatic check (FR-010).

### 4.7 `ReviewIssue` / `CheckFailure`

`ReviewIssue`: `{claim_id | None, kind: contradicted|unconfirmed|missing_log_check|other, detail ≤ 200, evidence_refs}`.
`CheckFailure`: `{check: str, item: str, detail: str}` — `check` ∈ `ability_unknown`,
`cooldown_mismatch`, `patch_mismatch`, `season_mismatch`, `source_env`, `source_prehotfix`,
`claim_unreferenced`, `log_check_missing`, `brief_too_long`, `guide_extra_claim`.

## 5. Agent-side registry (`wcl_agent/guide_meta.py`, dataclasses)

`wcl_agent` must not import the backend (dependency direction backend → wcl_agent). The
existing in-process registry becomes a **provider hook**:

```python
@dataclass(frozen=True)
class BriefRecord:
    class_name: str; spec: str; content_type: str
    text: str                    # render_brief_text output (already within budget)
    cooldowns: tuple[GuideCooldown, ...]
    game_patch: str | None; season: str | None
    generated_at: datetime | None
    freshness: str               # current | possibly_stale | unknown
    data_sufficient: bool

BriefLoader = Callable[[str, str, str], Awaitable[BriefRecord | None]]
def set_brief_loader(fn: BriefLoader) -> None
async def get_brief(class_name, spec, content_type) -> BriefRecord | None
```

The backend registers a loader at startup that reads the published brief from the DB
through a short in-process TTL cache (60 s), so a guide published by another instance is
seen within a minute and no registry warm-up is needed (replaces `load_guide_registry`'s
role; `GuideMeta`/`get_guide_meta` are folded into `BriefRecord`/`get_brief`). The CLI
leaves no loader set → `None` → tools fall back to measured-data-only coaching (unchanged
behaviour).

## 6. Roster (`wcl_agent/roster.py`)

```python
@dataclass(frozen=True)
class RosterSpec: class_name: str; class_display: str; spec: str; role: str  # tank|healer|dps
@dataclass(frozen=True)
class Roster: specs: tuple[RosterSpec, ...]; source: Literal["game_data", "fallback"]
```

- `load_roster()` (async): WCL `gameData.classes` through a new feature-014 cache family
  `game_classes` (TTL 24 h, key `wcl:game_classes:v1`), mapped to WCL filter values;
  falls back to the static `CLASS_SPECS` map (which gains `"Devourer"`) on any error.
- `roster_snapshot()` (sync): the last loaded roster or the fallback — for sync call sites
  (`role_for_spec`, `normalize_class_name`, request validation).
- Role: tank/healer sets stay in `constants.py`; any spec not in them is `dps` (Devourer).

## 7. Cache families (feature 014 `get_or_load`)

| Family | Key | TTL | Value |
|---|---|---|---|
| `game_classes` | `wcl:game_classes:v1` | 24 h | roster rows |
| `spec_datasheet` | `wcl:datasheet:v1:{content_type}:{class}:{spec}:{patch_or_season}` | 12 h | `DataSheet` |
| `guide_research` | `guide:research:v1:{content_type}:{class}:{spec}:{patch}:{hotfix_ts}` | 6 h | `FactSheet` |
| `live_version` | `ext:wow_version:v1:{region}` | 15 min | `{build, version, fetched_at}` |
| `hotfix_feed` | `ext:hotfix:v1` | 30 min | `{article_url, latest_at, entries[{date, class_name, specs[] (empty = whole class)}]}` |
| `talent_names` (optional) | `ext:talents:v1:{build}` | 7 d | `{talent_id: name}` (research R5 §6, off by default) |

The patch/season/hotfix in the key gives FR-054's invalidation for free: a new patch,
season or hotfix produces a new key.

## 8. Accuracy check data (`backend/evals/guides/`)

- `facts/<content_type>/<Class>-<Spec>.json`: `[{id, statement, expected: "present"|"absent", match: [keywords], notes}]`.
- `adversarial/*.json`: the six misleading cases (FR-021) as fixtures (fake evidence items /
  stored guides) with the expected outcome.
- `coaching/*.json`: `{report_code, fight_id | null, player, content_type, question, expected_points: [{id, must: "raise"|"not_contradict", keywords}]}`.
- Reports are written to `backend/evals/guides/reports/<timestamp>.json` + `.md`
  (gitignored except `baseline.json`).
