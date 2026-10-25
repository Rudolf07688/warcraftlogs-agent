# Contract: `wcl_agent` import paths after feature 018

The importer contract is the module path. Old flat paths of moved modules no longer
exist (no shims). Package `__init__.py` files export nothing, so always import the module:
`from wcl_agent.cache import cache`, never `from wcl_agent import cache`.

| Old import path | New import path |
|---|---|
| `wcl_agent` | unchanged (imports `agent`) |
| `wcl_agent.agent` | unchanged |
| `wcl_agent.cli` | unchanged |
| `wcl_agent.menu` | unchanged |
| `wcl_agent.wcl_client` | `wcl_agent.client.wcl_client` |
| `wcl_agent.queries` | `wcl_agent.client.queries` |
| `wcl_agent.aio` | `wcl_agent.client.aio` |
| `wcl_agent.cache` | `wcl_agent.cache.cache` |
| `wcl_agent.cache_models` | `wcl_agent.cache.cache_models` |
| `wcl_agent.normalize` | `wcl_agent.cache.normalize` |
| `wcl_agent.tools` | `wcl_agent.tools.tools` |
| `wcl_agent.report_tools` | `wcl_agent.tools.report_tools` |
| `wcl_agent.benchmark` | `wcl_agent.tools.benchmark` |
| `wcl_agent.cooldowns` | `wcl_agent.tools.cooldowns` |
| `wcl_agent.fight_time` | `wcl_agent.tools.fight_time` |
| `wcl_agent.provenance` | `wcl_agent.tools.provenance` |
| `wcl_agent.guide_meta` | `wcl_agent.guides.guide_meta` |
| `wcl_agent.guides_tool` | `wcl_agent.guides.guides_tool` |
| `wcl_agent.models` | `wcl_agent.llm.models` |
| `wcl_agent.model_retry` | `wcl_agent.llm.model_retry` |
| `wcl_agent.vertex` | `wcl_agent.llm.vertex` |
| `wcl_agent.genai_compat` | `wcl_agent.llm.genai_compat` |
| `wcl_agent.context_trim` | `wcl_agent.llm.context_trim` |
| `wcl_agent.constants` | `wcl_agent.game.constants` |
| `wcl_agent.roster` | `wcl_agent.game.roster` |
| `wcl_agent.patch` | `wcl_agent.game.patch` |

The same mapping applies to file paths (`wcl_agent/x.py` → `wcl_agent/<pkg>/x.py`), dotted
patch strings and logger names (`logging.getLogger(__name__)`).
