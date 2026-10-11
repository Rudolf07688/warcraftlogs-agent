# US5 review — guide freshness (quickstart "US5" steps 1–3)

Automated: `backend/tests/test_guide_meta.py` (freshness rule, current patch from a faked
menu, guide-meta block parse/strip/validation, registry round-trip, preamble labels),
`backend/tests/test_spec_guides.py` (provenance persisted + registry on success, exactly one
repair turn on the same session, failed repair ⇒ NULL metadata but guide ready, failed
generation leaves provenance untouched, startup registry load, roster freshness, API
freshness + sources), `test_guide.py`, `test_profile_context.py` — **pass**.
Migration `0009_guide_provenance` applied to the local Postgres (`alembic current` = head).
`npm run build` green with the Class Guides changes.

Manual steps need the running app (restart the backend so the registry loads and the
new columns are read).

| Step | Check | Result | Notes |
|---|---|---|---|
| 1 | Profile → Class Guides: pre-existing guides show **Patch unknown** + "May be out of date"; regenerate one → **Patch 12.1** + generated date + sources | _pending_ | current patch probed live = "12.1" (zone 53) |
| 2 | Coaching question for a spec with an unknown-patch guide → advice drawn from it flagged as possibly outdated (heading label `guide patch unknown · may be out of date`) | _pending_ | |
| 3 | **Content check**: the regenerated guide states its patch, has a "Major cooldowns" section with ≥3 numeric cooldowns, and `spec_guides.major_cooldowns` is populated (`SELECT class_name, spec, game_patch, jsonb_array_length(major_cooldowns) FROM spec_guides WHERE status='ready'`) | _pending_ | guide model default `gemini-3.6-flash` (web search ⇒ sources); a Claude guide model yields `sources = []` |
