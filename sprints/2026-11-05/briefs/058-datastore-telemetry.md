# Brief 058: data-store telemetry (Postgres, Redis, slow-query links, D9–D11, local alerts)

- **Feature / branch:** 058, `058-datastore-telemetry`
- **Tier:** M (one Spec Kit pass: specify → plan → tasks → implement, no gates; answer your own clarify questions and record them on the board)
- **Seat:** `dev-1` (Ansel). Parallel developers: Nils (dev-3) on 059 runtime profiles and dashboards, Tomas (dev-2) on 060 frontend, build-vs-runtime and redaction e2e. Read the board's `contract:*` and `owner:*` keys first: they bind you.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (detached at the base). Base ref: sprint branch tip `sprint-2026-11-05` = `6437aa2`. Create your branch there.
- **Security-core: yes.** You add a database role and a new log path into Loki. A `qa-security` review runs on your diff at hand-off. What must never happen: SQL parameter values, literals or credentials from the slow-query log reaching Loki unmasked; the exporter connecting as a superuser or the table owner when a `pg_monitor` role does the job; a DSN or password in the repo, in Alloy's UI/logs or in a metric label; Redis key names (they can carry account ids) becoming labels (no `check_keys`).
- **Migration:** `0022_pg_stat_statements` (`down_revision = "0021_raw_fetch_own_summary"`), yours alone. Use it for `CREATE EXTENSION pg_stat_statements` and, if you choose one, the monitoring role (the way 0004 creates the runtime role from env vars).
- **Read first:** `specs/telemetry_spec.md` §7.2, §7.3, §7.4, §8.2 (D9–D11), §8.4, §9, §14. The stories below win where they differ.

## Stories, in this order (AC verbatim from Shortcut; drop order: alerts, then D9–D11)

### Postgres exporter with pg_stat_statements and pgvector queries (sc-417, 3)
- `pg_stat_statements` enabled; Alloy `prometheus.exporter.postgres` with the non-default collectors from §7.2.
- Custom queries for vector index size and embedding table rows.
- Top queries by total time and the knowledge-base index size are visible in Grafana.

### Redis exporter next to the app's cache hit ratio (sc-418, 1)
- Alloy `prometheus.exporter.redis` reports memory, evictions, keyspace hits/misses, clients and latency.
- Redis's hit ratio shows next to `app.cache.requests` hit ratio.

### sqlcommenter and slow-query log linked to traces (sc-419, 2)
- SQLAlchemy sqlcommenter appends `traceparent` to SQL.
- Postgres logs statements over 250 ms, lock waits and autovacuum, collected through Docker logs into Loki.
- A slow-query line opens its trace via a Loki derived field.

### Infra and meta-monitoring dashboards (D9, D10, D11) (sc-420, 3)
- cAdvisor container metrics and Alloy/Loki/Tempo/Mimir self-metrics are scraped.
- D9 (Postgres), D10 (Redis) and D11 (infra and meta) are provisioned; D11 shows Alloy drops and queue, ingest rates and active series against the 50k budget.

### Minimal local alerts: telemetry pipeline drops and daily build spend (sc-424, 1)
- Grafana-managed alert rules provisioned as code: Alloy exporter failures or dropped spans/logs; estimated Claude Code spend per day above a configurable threshold.
- Each rule fires on a synthetic trigger.

## PO notes (read the code before believing these)
- **Postgres logs go through the redaction pipeline,** never straight to `loki.write`: route them into the existing OTLP path (as the board does via `otelcol.receiver.loki` → stamp/redact) so `redact.ottl` applies. With asyncpg's extended protocol Postgres logs bound parameters in `DETAIL: parameters: …`; decide `log_parameter_max_length` (0 is the safe default) and prove a seeded secret in a slow query arrives masked or absent.
- **sqlcommenter and asyncpg:** `SQLAlchemyInstrumentor().instrument(enable_commenter=True, …)` makes every statement text unique (traceparent), which defeats asyncpg's prepared-statement cache and adds a prepare per query. The ADK session store shares the engine (`backend/app/db/session.py`). Measure it (a quick micro-benchmark against `pg.py` is enough) and choose the commenter options knowingly; record the choice as a board `decision`. Telemetry is off unless configured, so the off-path must stay byte-identical SQL.
- Postgres config: the db service's `command:` (`-c shared_preload_libraries=pg_stat_statements`, `log_min_duration_statement=250ms`, `log_lock_waits=on`, `log_autovacuum_min_duration=0`, JSON or a parseable line format). The owner's existing `pgdata` volume must start unchanged apart from the extension.
- Alloy has `prometheus.exporter.cadvisor`, `prometheus.exporter.self`, `.postgres` and `.redis` built in; scraping Loki/Tempo/Mimir's `/metrics` covers the rest. The series budget is 50k (§9): keep cAdvisor's label set small and drop what D11 doesn't need.
- Docker socket: if you mount it into Alloy (docker logs, cAdvisor), mount it read-only and say why on the board.
- **Panels with per-interval bars or legend totals** must use a window equal to the step (sc-471, a QA bug on the build dashboards: overlapping `increase` windows overcount by a third). Test it in your dashboard test.
- Dashboards query recording-rule aliases (your new file `observability/mimir/rules/anonymous/datastores.yaml`); D10 shows Redis's hit ratio next to the existing `cache:hit_ratio` alias.
- The test stack hard-codes host port 5432/6379 for db and redis; the owner's app stack uses them. Make them overridable with the existing defaults (e.g. `${DB_PORT:-5432}`) before your stack scripts start db or redis.

## File footprint (stay inside it; board `owner:stream-058`)
- `docker-compose.yml`: the `db`, `redis` and `alloy` service blocks; any new service goes directly after the `alloy` block (before the observability-profile comment). No new named volumes (ask on the board if you need one). Nils adds `pyroscope` after `grafana` and backend env vars; leave those hunks alone.
- `observability/alloy/config.alloy`: a new section appended at the end of the file under `// --- Data stores and infra (feature 058) ---`. Wiring into existing components by reference is fine; editing existing blocks is not (Nils owns the spanmetrics and `log_window` blocks).
- `observability/grafana/provisioning/datasources/datasources.yaml`: only the Loki `derivedFields` list (add your slow-query field). Nils owns the Tempo block and adds a Pyroscope datasource.
- `backend/app/telemetry/setup.py`: only the `SQLAlchemyInstrumentor().instrument(...)` line(s) in `instrument()`. Nils owns the rest of the file.
- `backend/app/db/session.py` (if the commenter needs engine options), `backend/migrations/versions/0022_pg_stat_statements.py`, `.env.example` (new variables, no values that work)
- New: `observability/postgres/**`, `observability/mimir/rules/anonymous/datastores.yaml`, `observability/grafana/dashboards/infra/**` (uids `wcl-d9-postgres`, `wcl-d10-redis`, `wcl-d11-infra`), `observability/grafana/provisioning/alerting/**`, `observability/test/datastores.sh`, `observability/test/alerts.sh` (+ helpers), `backend/tests/test_telemetry_datastores.py`, `mimir.yaml` if you need it
- `observability/README.md`: one new section `## Data stores, infra and alerts (058)`.
- `specs/058-datastore-telemetry/**`
- Nothing else (not `pyproject.toml`/`uv.lock` — the commenter ships with the installed SQLAlchemy instrumentation; not `provisioning.sh`, `loki.yaml`, `tempo.yaml`, runtime dashboards). Need something: ask on the board with key `owner:<path>`.

## Docker (explicit grant; overrides the developer file's "no docker compose")
- Only through `observability/test` scripts or `docker compose -p wcl-obs-ansel --profile observability ...`, on 25xxx host ports via the env overrides (board `contract:test-stacks`). You may start `db` and `redis` in your project on 25xxx ports. Never touch the `warcraftlogs-agent` project: it is live and observes this session. `down -v` after each run and before hand-off.
- Throwaway Postgres for the backend suite and the commenter benchmark: `pg.py up ansel`.

## Tests and proof
- `check.py run --as ansel` on your committed tree (receipt matters); `check.py run --pg ansel` for the migration (0 skipped), then `pg.py down ansel`.
- Scripts prove on a stack seeded with **real-shaped data** (an HNSW index with rows, a slow query > 250 ms carrying a traceparent comment, Redis hits and misses, an old row or two), asserting values, not presence: top statement by total time is the slow one; index size > 0 and equals `pg_relation_size`; Redis hit ratio matches the hits/misses you made; the slow-query line in Loki carries the trace id and the derived field resolves; a seeded secret in the slow query is masked; each alert goes Firing on its synthetic trigger and Normal again.
- Dashboard tests: JSON parses, every expr uses an alias from `datastores.yaml` or an existing rule file, query shape (rate vs increase, window = step, units).
- Live checks (team-lead runs them on the merged tip): post each as a board `question` with key `live-check:058` and exact steps.

## Hand-off
Stories to Under Review, a board `handoff`, and your final result: branch, commits, files, the `check.py` RESULT and RECEIPT lines, the commenter benchmark numbers, risks, and an AC-by-AC mapping. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
