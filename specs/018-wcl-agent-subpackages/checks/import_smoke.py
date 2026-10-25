"""FR-006 one-off: import every ``wcl_agent`` module and ``backend.app.main``.

Run from the repo root: ``uv run python specs/018-wcl-agent-subpackages/checks/import_smoke.py``.
Prints one line per module and exits 1 if any import fails.
"""

import importlib
import pkgutil
import sys
import traceback

import wcl_agent

names = ["wcl_agent"] + sorted(m.name for m in pkgutil.walk_packages(wcl_agent.__path__, "wcl_agent."))
names.append("backend.app.main")
failed = 0
for name in names:
    try:
        importlib.import_module(name)
        print(f"ok    {name}")
    except Exception:
        failed += 1
        print(f"ERROR {name}\n{traceback.format_exc()}")
print(f"{len(names)} modules, {failed} failed")
sys.exit(1 if failed else 0)
