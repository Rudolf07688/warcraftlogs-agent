# Brief 061-kb-embedding (tier S)

- Feature 061, branch `061-kb-embedding`. Seat dev-3 (Nils). Model opus, effort high.
- Worktree `/home/rudolf/dev/wcl-worktrees/dev-a`, base ref `sprint-2026-11-05b` (0678ea7).
- Parallel developers: Ansel (062, observability), Tomas (063, frontend), the dev-4 holder (064, agent instruction). Disjoint footprints.
- Not security-core. No migration.

## Footprint
`backend/app/kb/**`, `wcl_agent/llm/generation.py` (the `embed_texts` hunk only), `wcl_agent/llm/model_retry.py` (only if the embed retry policy is the cause), `backend/app/config.py` (kb_* settings only), `.env.example` (kb_* lines), new tests `backend/tests/test_061_*.py`, and existing kb/embedding tests that pin behaviour you change. Not `backend/app/agent_tools/**` (064 owns it). The D8 dashboard is Ansel's; if it needs a query change, ask on the board.

## Stories (acceptance criteria verbatim)

### Knowledge-base semantic search is always down: the query embedding hits its 3 s timeout (sc-428, 2 pts)
What happens: every `search_knowledge` call takes about 3.0 s. Its `embeddings gemini-embedding-001` span ends in `CancelledError` at exactly 3000 ms, which is `EMBED_TIMEOUT_S = 3.0` in `backend/app/kb/search.py` `_embed`. The backend logs `query embedding failed, keyword search only: TimeoutError`, and the agent tells the user that semantic search is down. Meanwhile the background indexer's embedding calls finish in about 100 ms. Not caused by telemetry (same on main's build with telemetry off).

Acceptance:
- The "guide" live-check prompt (livecheck.py) runs `search_knowledge` with the semantic leg on: no `query embedding failed` warning, and the embedding span finishes without error.
- A test pins the cause (whether that's sequential requests, client setup per call, or the wrong timeout).

### QA PERF-004: embed search_knowledge queries concurrently, not one Vertex request after another (sc-319, 1 pt)
Problem: with kb_embed_request_batch=1 the 1-5 query texts are embedded in sequential Vertex requests (~0.75-2 s before any SQL). Past the 3 s embed timeout, search falls back to keyword-only.
Suggested fix: send the per-query requests concurrently (bounded), or batch them when a live check confirms multi-input requests work for gemini-embedding-001.
(No formal AC on the ticket; I set it: a multi-query search issues its query embeddings concurrently (bounded), proven by a test with a slow fake provider whose total wall time is about one request, not N.)

### QA live: D8 records no failed embeddings when the 3 s query timeout cancels the call (sc-503, 1 pt)
`search.py` `_embed` wraps `embedder.embed` in `asyncio.timeout(EMBED_TIMEOUT_S=3.0)`; the timeout cancels the provider call, so `embedder.py` sees `CancelledError` (a BaseException) and its `except Exception` never records; the TimeoutError is raised outside. Live: 4 query embeddings failed with TimeoutError and `app_embedding_duration` only has `task=document`, so D8 stays blank during exactly the outage it should show.
Fix: record in a `finally` / `except BaseException` in the embedder (error.type `TimeoutError` or `cancelled`), or record in `search._embed` on the timeout. Test with a provider fake slower than the budget.

## My notes from reading the code (verify, don't trust)
- `VertexEmbedder.embed` loops `request_batch` texts per request, sequentially; `settings.kb_embed_request_batch` defaults to 1. But the live span ended at exactly 3000 ms as one span: a single request may itself be slow (retry policy `_POLICY` with backoff? client built per call? a cold-start or wrong region?). Find the real cause first: time one live query embedding with the stack up (Google ADC is valid today) before choosing the fix. Don't just raise the timeout unless that is the evidence.
- sc-503's fix must keep a cancelled call from recording twice, and the recorded label must pass the `METRIC_ATTRIBUTES` allowlist (see facts).
- Recording on cancellation must not swallow the `CancelledError` (re-raise it).

## Process (all streams)
- Tier S: post a short plan on the board (`decision`, key `plan:<NNN>`), then implement. No Spec Kit.
- Branch `<NNN>-<short-name>` from the base ref, in your worktree. Stay inside the footprint; if a root cause sits outside it, post a `question` on the board naming the file and hunk, and keep going on the rest.
- Move your stories to In Progress when you start and to Under Review in your hand-off (Team 1, Standard workflow: In Progress 500000008, Under Review 500000023). Never Done.
- **Team facts (P13 trial, first sprint):** run `python3 .claude/team/facts.py for <path>` before you change a file you haven't read yet; trust what it says, re-check anything marked STALE. When you learn something about this code that the next developer would otherwise rediscover (a trap, a contract, a non-obvious cause), add it with `facts.py add` and commit the fact file on your branch. Name the facts you used and the ones you added in the hand-off.
- Checks: `python3 .claude/team/check.py run --as <your-name>` on your final committed clean tree (the RECEIPT is what lets me merge without re-running). GitNexus `detect-changes --scope all` before each commit.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Never push. Never commit CLAUDE.md, AGENTS.md, todo.md, the constitution or .specify/feature.json.
- **Hand-off:** post a board `handoff` (key `status:<NNN>`) and return the same as your result: branch, commits, files, the check.py RESULT and RECEIPT lines, the AC-to-test mapping, risks, a **live-check** suggestion (prompt or action plus the expected facts), facts used/added, and one line starting `Retro:` (what helped or slowed you this run, for the team retro).

## Known facts for this footprint

Team facts for `backend/app/kb/`, `backend/app/kb/search.py`, `backend/app/kb/embedder.py`, `backend/app/config.py`, `wcl_agent/llm/generation.py` (`python3 .claude/team/facts.py for ...`). Trust them, but re-check one marked STALE before relying on it; record a new lesson with `facts.py add`.

- **embed-timeout-cancel-unrecorded** (direct: sym:backend/app/kb/search.py::_embed is inside backend/app/kb/; verified b9cf9a3 2026-11-05): KB search wraps the query embedding in `asyncio.timeout(EMBED_TIMEOUT_S)` (3.0 s). The timeout cancels the provider call, so `VertexEmbedder.embed` sees `CancelledError`, which its `except Exception` doesn't catch, and records nothing. Timed-out query embeddings leave no `app_embedding_*` series (sc-503). Live query embeddings take about 3 s on this host, so semantic search keeps falling back to keywords (sc-428).
- **telemetry-config-no-app-config** (direct: file:backend/app/config.py; verified b9cf9a3 2026-11-05): Importing `backend.app.config` loads ADK and FastAPI, and telemetry has to start before both. So `backend/app/telemetry/config.py` reads `os.environ` itself (it loads `.env` the way config.py does and honours `WCL_LOAD_DOTENV`) and must never import `backend.app.config`. A setting the telemetry bootstrap needs goes into its own env read, not into `Settings`.
- **uploader-text-neutralise** (direct: file:backend/app/kb/search.py is inside backend/app/kb/; verified b9cf9a3 2026-11-05): Uploader-controlled WCL text (player names, report titles, guilds) reaches the model only through `report_tools.neutralise`, then a cap (`_bounded`/`_bounded_strings`, `MAX_NAME_CHARS`). KB search uses the same neutraliser for its `<data>` blocks. Neutralise after projecting down to the fields you return (QA PERF-001), and cap after neutralising, because NFKC can lengthen text.
- **wcl-agent-no-backend-imports** (file: file:wcl_agent/ contains wcl_agent/llm/generation.py; verified b9cf9a3 2026-11-05): `wcl_agent` never imports `backend`: it runs standalone, and only backend may import wcl_agent. So OTel instruments for wcl_agent code live in wcl_agent (`app.cache.requests` in `cache.py`, the GenAI spans in `generation.py`; OTel API only, no-ops without a provider), and shared helpers move into wcl_agent (`neutralise` in report_tools, `DIFFICULTY_NAMES` in `wcl_agent/game`).
- **dialect-sql-compiles** (neighbour: sym:backend/app/repositories/raw_fetches.py::fetch_visible_clause called by backend/app/kb/search.py::_chunk_where; verified b9cf9a3 2026-11-05): Dialect-specific SQL inside a clause with a fixed signature is written as a `ColumnElement` subclass with one `@compiles` per dialect. In `raw_fetches.py`, `_NonEmpty` uses `jsonb_array_length` on Postgres and `json_array_length` on SQLite, and `_CodesVisible` works the same way. Callers keep one function that runs on both test engines.
- **fetch-visible-clause-one-rule** (neighbour: sym:backend/app/repositories/raw_fetches.py::fetch_visible_clause called by backend/app/kb/search.py::_chunk_where; verified b9cf9a3 2026-11-05): Visibility for the global tables (`raw_fetches`, `kb_chunks`) lives in the SQL of every read branch, and it has one definition: `raw_fetches.fetch_visible_clause`, the 039 rule (every code public or granted to the tenant since `since`). Rows derived from a fetch must also pass `fetch_names_code` (a chunk's `report_code` is one of its fetch's codes). Join these two; never re-implement the rule.
- **metric-attributes-allowlist** (neighbour: file:backend/app/telemetry/metrics.py called by backend/app/kb/search.py::search; verified b9cf9a3 2026-11-05): A backend metric label survives only if its key is in `setup.METRIC_ATTRIBUTES`: one global allowlist, applied through a View to every instrument, library ones included. New app attributes are enums namespaced `app.*` (`app.cache.name`, `app.rag.index`), because a bare key like `result` would let any library's attribute of that name through. `session.id` is never a metric label.
- **raw-fetches-no-query-text** (neighbour: file:backend/app/repositories/raw_fetches.py called by backend/app/kb/search.py::_chunk_where; verified b9cf9a3 2026-11-05): `raw_fetches` rows keep the params, report codes and payload, never the GraphQL query text. Anything that depends on the query's shape has to be decided when the row is written, the way `own_summary` is, or inferred from the body. The KB backfill skips stored tables whose metric it can't infer from the body.
