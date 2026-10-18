# Quickstart: Live Model Discovery

How to check the feature end to end. Commands run from the repo root.

## 1. Unit tests (no network)

```bash
uv run --extra test pytest -q backend/tests/test_models.py backend/tests/test_guides_and_boot.py \
  backend/tests/test_cache_families.py
uv run --extra test pytest -q          # full suite: static-mode tests must still pass
```

Fixtures: `backend/tests/fixtures/model_catalog_google.json` and
`model_catalog_anthropic.json` (recorded 2026-10-18 listings). The tests cover:

- classification yields exactly the per-class candidates in the plan's table;
- `keep` = 2 / 1;
- a 404 on haiku-5-5 falls back to haiku-4-5;
- a 429 stops the class after one retry;
- EXPERIMENTAL is dropped, and GA beats preview on a version tie;
- both `versionId` forms (bare and `@date`);
- a listing failure gives `fallback` (not degraded), and nothing passing gives `degraded`;
- the default falls back to the newest flash;
- cache hit, cache miss, and TTL `0`;
- the probe carries a tool declaration;
- every client factory uses `model_location()`.

## 2. Live check

```bash
# .env: WCL_MODEL_DISCOVERY=catalog, WCL_MODEL_LOCATION=global, GOOGLE_CLOUD_LOCATION=europe-west1
docker compose exec redis redis-cli --scan --pattern 'ext:models:*' | xargs -r docker compose exec -T redis redis-cli del
docker compose up --build backend
```

Expect in the backend log:

```text
INFO: wcl_agent.models: gemini pro: gemini-3.1-pro-preview, gemini-2.5-pro
INFO: wcl_agent.models: gemini flash: gemini-3.8-flash, gemini-3.7-flash
INFO: wcl_agent.models: gemini flash-lite: gemini-3.5-flash-lite, gemini-3.1-flash-lite
INFO: wcl_agent.models: claude haiku: no quota (429)      # until Claude quota is granted
INFO: wcl_agent.models: claude sonnet: no quota (429)
INFO: wcl_agent.models: claude opus: no quota (429)
… boot step "models": 6 models (catalog)
```

Then:

1. `GET /api/models` (signed in) lists those six, with default `gemini-3.8-flash` unless
   `WCL_DEFAULT_MODEL` survived.
2. Send a chat turn on `gemini-3.8-flash` that needs a tool, for example "how is
   <character> on <realm> doing?". It completes.
3. Generate a report, open a class guide, and trigger follow-up suggestions. All of them
   succeed while `GOOGLE_CLOUD_LOCATION=europe-west1`.
4. Restart the backend. The step detail reads `6 models (catalog, cached)` and no probe
   lines appear before it.
5. After the Claude quota is granted: clear the key as above and restart. Haiku, sonnet
   and opus appear.

## 3. Fallback check

```bash
WCL_MODEL_LOCATION=global GOOGLE_CLOUD_PROJECT=does-not-exist-123 docker compose up backend
```

Expect exactly one `model catalog unavailable … probing the static lists` warning, then
today's static behaviour. The dropdown is non-empty, and the result is not degraded
unless every static model also fails.

## 4. Before committing

```bash
uv run --extra test pytest -q
npm run build --prefix frontend
node .gitnexus/run.cjs detect-changes --scope all --repo .
```
