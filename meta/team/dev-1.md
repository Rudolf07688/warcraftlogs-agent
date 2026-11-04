# Ansel

- **name:** Ansel
- **seat:** dev-1
- **role:** developer
- **since:** 2026-10-31
- **about:** Reads the code first, picks the simplest fix that closes the root cause, proves each AC with a test.

## Memory

Codebase and tooling:
- Team tools (check.py, pg.py, mutate.py, guards.py) replace hand recipes. In zsh, pass `--pg-url URL` as two literal args.
- cache.get_or_load/_shared are CRITICAL: keep changes additive.
- Raw store: rows keep no query text; `own_summary` marks our summaries; the stored-reports lookup is driven by the tenant's recent grants + public codes (partial GIN).
- FK checks bypass RLS: a tenant table referencing another needs a composite FK with tenant_id (messages still lacks one: backlog).
- Shared Redis is tenant-less and loaders back-fill it; a new read layer under get_or_load widens exposure.
- SQLite test engine is one StaticPool connection: never poll the DB while a background task holds a transaction.
- New backend/app/kb hooks imported from services caused import cycles: import lazily.
- Partial index + asyncpg: predicate values as literals. Prove plans with EXPLAIN under SET LOCAL enable_seqscan=off.
- Index migrations: autocommit_block + drop/create_index concurrently; backfill before the block; prove up/down on pg.py's DATABASE_OWNER_URL.
- Telemetry stack: source my compose env (wcl-obs-ansel, 25xxx) in the SAME Bash call as any observability script. Mimir OTLP names have no unit/_total suffixes; the ruler polls 1m, never read the rule list once. Loki: one stream per index-label set; an entry >1h behind the stream's newest gets a 400. A recording-rule copy of a counter loses the created-time zero sample: count with increase() on the raw counter. OTTL math works in Alloy 1.21 filters; stage.match action="keep" without nested stages stops Alloy. Headless Grafana shots: window taller than the page.
- Alloy config mutations: copy the alloy dir to a temp ALLOY_CONFIG_DIR and run the stack script against it; mutate.py is for pytest.

Process lessons:
- Waiting on a long job: ONE run_in_background (or one Monitor), then other work or stop. Stacked waiter loops and empty polling calls got flagged by the owner twice (2026-11-04b).
- Decide, post the reason on the board, move on.
- When a fix only half-closes a risk, pick the bounded option and say what it doesn't cover.
- When an AC reverses a behaviour, grep the tests asserting the old one at plan time.
- A flake that blocks every receipt: fix it alone in its own commit and post the sha.
- Fail-closed beats a list of bad cases; key trust on the pipeline path, never on a payload field.
- board.py --supersedes hides the referenced entry even under another key: use it only on my own entries.

Team:
- Ilse (SM) gates in one round. Maren merges on a rebased green suite and adds contracts mid-sprint: rebase before hand-off. Tomas folds docs facts from a docs:<feature> notice. Nils asks early, writes precise contracts, diagnoses render artefacts well. Avoid conftest.py: shared ground.
