# Data model: package layout

No runtime data changes. The "entities" are the packages and what they hold.

| Package | Holds | Depends on (imports from) |
|---|---|---|
| `wcl_agent` (top) | `agent` (root agent), `cli` (console entry), `menu` (encounter menu, `load_world_zones`) | all sub-packages |
| `client` | WCL API: `wcl_client`, `queries`, `aio` | `cache` |
| `cache` | shared Redis cache: `cache`, `cache_models`, `normalize` | — |
| `tools` | ADK function tools: `tools`, `report_tools`, `benchmark`, `cooldowns`, `fight_time`, `provenance` | `client`, `cache`, `game`, `guides`, top `menu` |
| `guides` | coaching briefs: `guide_meta`, `guides_tool` | `tools` (`provenance`), `game` (`roster`) |
| `llm` | chat models: `models`, `model_retry`, `vertex`, `genai_compat`, `context_trim` | `cache` |
| `game` | WoW reference data: `constants`, `roster`, `patch` | `client`, `cache`, top `menu` |

Rules:

- Each sub-package has an `__init__.py` with a one-line docstring and nothing else.
- The import edges between modules are the ones at base; only their spelling changes.
  Existing cycles (e.g. `constants` ↔ `roster`, broken by a lazy import) stay as they are.
