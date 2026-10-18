# Feature Specification: Shared Warcraft Logs Cache

**Feature Branch**: `014-redis-wcl-cache`

**Created**: 2026-10-18

**Status**: Draft

**Input**: User description: "We are going to implement a caching layer with redis. Please remember to include all the new things in the docker compose setup. Please see `documentation/redis_cache_spec.md` for the full spec"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Faster answers for repeated character and report questions (Priority: P1)

A raider asks the chat agent about a character ("how is Rudolf on Area 52 doing?") or a raid report ("how did I do in last night's raid?"). If that same character or report was looked up recently — by them or by anyone else — the agent answers from the shared cache instead of asking Warcraft Logs again, so the answer comes back faster and spends none of the Warcraft Logs request quota.

**Why this priority**: This is the core value of the feature: lower latency and protection of the Warcraft Logs rate limit. Everything else (metrics, refresh) supports it.

**Independent Test**: Ask the same character question twice within a few minutes; the second answer arrives noticeably faster and no new Warcraft Logs request is recorded for the cached data.

**Acceptance Scenarios**:

1. **Given** a character was looked up less than 24 hours ago, **When** any user asks about that character again, **Then** the name-to-character resolution is served from the cache with no Warcraft Logs request.
2. **Given** a finished raid report was summarised less than 24 hours ago, **When** any user asks about that report, **Then** the summary and per-player figures are served from the cache.
3. **Given** a character's recent-report list was fetched more than 5 minutes ago, **When** a user asks about their latest raid, **Then** the list is fetched fresh from Warcraft Logs and re-cached.
4. **Given** ten users ask about the same uncached character at the same moment, **When** their requests arrive together, **Then** Warcraft Logs is queried once and all ten receive the same answer.
5. **Given** a user mistypes a character name that does not exist, **When** they (or someone else) repeat the same misspelt name within 60 seconds, **Then** the "not found" result is returned without asking Warcraft Logs again.

---

### User Story 2 - The chat keeps working when the cache is unavailable (Priority: P1)

The cache is an optimisation, never a dependency. If the cache service is stopped, unreachable, or returns corrupted data, users still get correct answers, just at uncached speed.

**Why this priority**: A cache outage that breaks the chat would make the feature a net negative; this must hold from day one.

**Independent Test**: Stop the cache service while the app is running, ask a character question, and confirm a correct answer is returned and the failure is counted.

**Acceptance Scenarios**:

1. **Given** the cache service is down, **When** a user asks a question, **Then** the answer is fetched directly from Warcraft Logs, the user sees no error, and a cache-unavailable outcome is counted.
2. **Given** a cached entry is corrupted, **When** it is read, **Then** it is discarded, the data is reloaded from Warcraft Logs, and an error outcome is counted.
3. **Given** Warcraft Logs itself is down and the data is not cached, **When** a user asks a question, **Then** the agent explains that Warcraft Logs is unavailable (no stale data is served).
4. **Given** caching is switched off by configuration, **When** users ask questions, **Then** every lookup goes straight to Warcraft Logs and behaviour is otherwise unchanged.

---

### User Story 3 - Operator sees how well each kind of cached data performs (Priority: P2)

The operator opens an internal statistics view and sees, for each kind of cached data and over a chosen window (for example the last 7 days), how often the cache answered, how often it missed, how slow the misses were, how many errors occurred, and whether the hit rate is healthy or needs review. Overall cache-service health (memory used, evictions) is shown alongside.

**Why this priority**: Without per-kind numbers the operator cannot tune freshness windows or decide whether a kind of data is worth caching at all. It is needed before the weekly review, but the cache delivers value without it.

**Independent Test**: Generate a known mix of hits and misses, open the statistics view, and confirm the counts, hit rates and status labels match.

**Acceptance Scenarios**:

1. **Given** cache activity over the last 7 days, **When** the operator requests statistics for 7 days, **Then** each cached data kind shows hits, misses, hit rate, average load time, errors, and a status of "ok" or "review".
2. **Given** a data kind's hit rate is below its review threshold, **When** statistics are shown, **Then** that kind is labelled "review".
3. **Given** a non-operator user, **When** they try to open the statistics view, **Then** access is refused.
4. **Given** the cache service was wiped, **When** statistics are requested, **Then** the view still loads and shows only the history recorded since the wipe.

---

### User Story 4 - User can force a fresh lookup (Priority: P3)

A user who suspects the answer is out of date ("check again", "refresh that") can ask the agent to bypass the cache for a character. The agent reloads the data from Warcraft Logs and replaces the cached copy for everyone. Because the cache is shared, a user can only force a refresh of the same character once per minute.

**Why this priority**: Useful on raid nights when logs are uploaded mid-session, but the short freshness window on recent reports already covers most of this need.

**Independent Test**: Ask about a character, ask the agent to check again, and confirm fresh data was fetched; ask to check again within a minute and confirm the cached copy is used instead.

**Acceptance Scenarios**:

1. **Given** cached character data, **When** a user explicitly asks to refresh it, **Then** the data is reloaded from Warcraft Logs and the cached copy is overwritten.
2. **Given** the user already forced a refresh of that character less than a minute ago, **When** they ask again, **Then** the cached copy is used and the agent says a refresh was done moments ago.

---

### User Story 5 - Developers get the cache with the standard local stack (Priority: P2)

A developer runs the usual single command to bring up the local stack and gets the cache service along with the database, backend and frontend, already wired to the backend, with sensible memory limits and no extra manual steps.

**Why this priority**: Explicitly requested; without it, nobody can run or test the feature locally.

**Independent Test**: From a clean checkout, bring the local stack up and confirm the backend reports a connected cache and the second identical question is a cache hit.

**Acceptance Scenarios**:

1. **Given** a clean checkout with the standard environment file, **When** the developer brings up the local stack, **Then** the cache service starts, becomes healthy, and the backend connects to it without manual configuration.
2. **Given** the cache service container is removed and recreated, **When** the stack restarts, **Then** the app works normally with an empty cache (no persistent data is required).

---

### Edge Cases

- Character names differing only by case or surrounding spaces ("Rudolf", "rudolf ") must resolve to the same cached entry.
- A raid report that is still in progress (live logging) must not be cached for 24 hours; it is either not cached or cached for at most 2 minutes.
- The concurrent-lookup coordinator holds a lock but the lookup is slow: waiting callers give up after about 2 seconds and fetch for themselves (counted as a lock timeout) rather than hanging.
- A Warcraft Logs lookup fails while others are waiting on it: the lock is released, the error is counted and surfaced, and nothing is written to the cache.
- Many entries written at the same time must not all expire at the same moment (expiry times are spread by up to 10%).
- The shape of cached data changes in a new release: old entries are ignored (versioned) and expire on their own.
- The cache service runs out of memory: least-recently-used entries are evicted; correctness is unaffected.
- The access credential for Warcraft Logs expires: it is reused until 60 seconds before expiry, then renewed.
- Metrics counters fail to record: the user's request still succeeds (metrics are fire-and-forget).

## Requirements *(mandatory)*

### Functional Requirements

**Cached data**

- **FR-001**: System MUST cache exactly these seven kinds of Warcraft Logs data, each with its own freshness window:
  | Kind | Contents | Freshness |
  |---|---|---|
  | Character identity | name/realm/region → character id, name, realm, region, class | 24 hours |
  | Character overview | gear, progress and parse summary | 10 minutes |
  | Character recent reports | list of recent reports (code, title, start time, zone) per list size | 5 minutes |
  | Report summary | fights, bosses, kills/wipes, roster | 24 hours |
  | Report player detail | one player's damage, healing, deaths, top abilities in a report | 24 hours |
  | Warcraft Logs access credential | API access token | until 60 s before it expires |
  | World zone list | raid zones, encounters, difficulties, partitions (drives the current-patch label and encounter lookup) | 1 hour |
- **FR-002**: Each freshness window MUST be overridable per kind by configuration, and every cached entry's expiry MUST be randomly extended by 0–10% (configurable) so entries written together do not expire together.
- **FR-003**: Character names and realms MUST be normalised (trimmed, lower-cased) before being used to identify a cached entry.
- **FR-004**: Cached entries MUST store the application's own normalised data, never raw Warcraft Logs responses, and MUST carry a format version so that a format change makes old entries ignored rather than misread.
- **FR-005**: Report data MUST only be cached for the full window when the report is finished; reports still in progress MUST be either not cached or cached for at most 2 minutes.
- **FR-006**: A "character not found" result MUST be cached for 60 seconds (configurable) and counted as a separate outcome from a normal hit.
- **FR-007**: System MUST NOT cache event-level combat data, rankings across arbitrary filters, the agent's final answers, or conversation state.
- **FR-008**: Cache entries for public Warcraft Logs data MUST be shared across all users and tenants, and the identity of a cached entry MUST NOT contain any user, tenant or conversation identifier. This deliberately supersedes feature 006 FR-019 (tenant-scoped WCL cache) for Warcraft Logs data; the per-tenant cache scoping is removed.

**Lookup behaviour**

- **FR-009**: All access to the cache for these seven kinds MUST go through one shared lookup path, so no lookup can bypass the counting of outcomes.
- **FR-010**: When several requests miss the same entry at once, only one MUST fetch from Warcraft Logs; the others MUST wait up to about 2 seconds for its result, then fetch for themselves and record a lock timeout.
- **FR-011**: If a Warcraft Logs fetch fails, nothing MUST be cached, any concurrency lock MUST be released, the error MUST be counted, and the failure MUST be surfaced to the agent as an explainable tool error.
- **FR-012**: If the cache service is unavailable or errors, the system MUST fetch directly from Warcraft Logs, skip cache writes, count a cache-unavailable outcome, and log it; users MUST NOT see an error caused by the cache.
- **FR-013**: A corrupted cached entry MUST be deleted, treated as a miss, and counted as an error.
- **FR-014**: Caching MUST be switchable off entirely by configuration, for comparison and incident response.
- **FR-015**: Users MUST be able to request a forced refresh of a character's data through the agent; this MUST bypass the cached copy, reload, and overwrite it, and MUST be limited to one forced refresh per user per character per minute.
- **FR-016**: Every real Warcraft Logs request MUST record the API points it spent, so the effect of caching on quota use is visible in logs.
- **FR-017**: Warcraft Logs requests MUST be retried with backoff on rate-limit and server errors, at most 2 retries.

**Metrics**

- **FR-018**: System MUST count, per data kind and per UTC day: hits, misses, not-found hits, lock timeouts, errors, cache-unavailable events, total load time and number of loads.
- **FR-019**: Daily counters MUST be retained for 35 days (configurable), kept separate from cached data, and recording them MUST NOT slow down or fail the user's request.
- **FR-020**: System MUST provide an internal, operator-only statistics view that, for a requested window of days (default 7), reports per data kind: hits, misses, hit rate ((hits + not-found hits) / (hits + not-found hits + misses)), average load time, errors, and a status.
- **FR-021**: Status MUST be "review" when the hit rate falls below the kind's threshold: 90% for character identity, access credential and world zone list; 60% for character overview and recent reports; 40% for report summary and player detail; otherwise "ok".
- **FR-022**: The statistics view MUST also show overall cache-service health: overall hit rate, evicted entries, and memory used.

**Local environment and configuration**

- **FR-023**: The local multi-service development setup MUST include the cache service, with a health check, an explicit memory limit, least-recently-used eviction, and no data persistence; the backend MUST be wired to it and wait for it to be healthy.
- **FR-024**: All new settings (cache location, on/off switch, per-kind freshness overrides, expiry jitter, lock duration, not-found duration, metrics retention) MUST be documented with defaults in the environment template and the setup must start with those defaults.

**Existing in-process cache**

- **FR-025**: The existing in-process Warcraft Logs query cache MUST be removed entirely; the shared cache is the only Warcraft Logs cache. Queries outside the seven cached kinds (e.g. leaderboards, rankings, ad-hoc queries) go to Warcraft Logs uncached.
- **FR-026**: Warcraft Logs API point usage for queries outside the seven cached kinds MUST remain visible in logs (FR-016), so any quota increase caused by removing the in-process cache can be measured and used as evidence for adding a cached kind.

### Key Entities

- **Cached entry**: a normalised piece of public Warcraft Logs data belonging to one of the seven kinds, identified by kind, format version and its natural identifiers (region/realm/name, character id, report code, list size, player id), with an expiry time.
- **Not-found marker**: a short-lived entry recording that a character name does not exist.
- **Daily counter set**: per data kind per UTC day, the outcome counts and load-time totals; expires after the retention period.
- **Cache statistics report**: the derived per-kind view (counts, hit rate, average load time, status) over a window, plus overall cache-service health.
- **Refresh allowance**: per user and character, the time of the last forced refresh, used to enforce one refresh per minute.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A repeated question about a recently looked-up character or finished report is answered at least 50% faster than the first time it was asked.
- **SC-002**: Replaying a realistic set of 100 chat questions uses at least 40% fewer Warcraft Logs API points than the same replay with caching switched off.
- **SC-003**: Ten simultaneous requests for the same uncached data produce exactly one Warcraft Logs request.
- **SC-004**: With the cache service stopped, 100% of questions that succeed with it running still succeed, and users see no cache-related errors.
- **SC-005**: After one week of normal use, the operator can read the hit rate and health status of all seven data kinds from the statistics view in under a minute.
- **SC-006**: A developer can bring up the full local stack, cache included, with the existing single start command and no extra manual steps.
- **SC-007**: The app stays within the Warcraft Logs rate limit during a typical raid-night evening of use.

## Clarifications

### Session 2026-10-18

- Q: Should cached public data be shared across tenants, or stay tenant-isolated (feature 006 FR-019)? → A: Shared across all tenants; no user/tenant id in cache identity; supersedes FR-019 for WCL data.
- Q: How does the shared cache relate to the existing in-process cache? → A: Replace it entirely; non-cached kinds go to Warcraft Logs uncached.
- Q: (plan) The zone list is fetched on every chat turn and would lose its cache under B. Add it? → A: Yes, as a 7th kind (world zone list, 1h); the per-turn repeated call is the measured reason. Report tables/graphs and leaderboards stay uncached.

## Assumptions

- The cache technology is Redis, as decided in `documentation/redis_cache_spec.md`; that document is the authoritative design reference for key formats, lock mechanics and counter layout during planning.
- For local development the cache runs as a container in the existing Docker Compose stack; provisioning a managed cache for production (e.g. Memorystore) is out of scope for this feature.
- The cache is disposable: losing its contents costs only speed and metrics history, never correctness.
- "Operator" means an authenticated user with an admin/operator role, or an internal-only route not exposed publicly; the existing authentication mechanism is reused.
- Users mostly look up their own and their guild's characters; if lookups turn out to be mostly arbitrary, hit rates for character data will be lower and freshness windows will be tuned in the weekly review.
- A 5-minute staleness for "latest raid" questions is acceptable; users needing up-to-the-minute data on raid night use the forced refresh.
- Prometheus/Grafana export is optional and out of scope; the stored counters plus the statistics view are sufficient.
- Rollout is staged: lookup path, metrics and statistics view first; then character identity and access credential; then the remaining five kinds; then a week of observation before the first review.
- Adding an eighth cached data kind requires measured evidence (a repeated, slow or rate-limited call in logs) and is out of scope here.
