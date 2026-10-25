"""FR-012 one-off: every ``wcl_agent`` reference resolves against the new tree.

Run from the repo root: ``uv run python specs/018-wcl-agent-subpackages/checks/ast_refs.py``.
Walks ``wcl_agent/**``, ``backend/**`` and ``main.py`` and checks:

* ``import wcl_agent...`` / ``from wcl_agent... import n`` and relative imports inside
  ``wcl_agent``: the module exists and ``n`` is a submodule or an existing attribute;
* string literals starting with ``wcl_agent.`` (patch targets, logger names): the longest
  importable prefix is a module and the rest is an attribute chain on it (logger names
  resolve to the module itself);
* no import binds the ``wcl_agent.cache`` or ``wcl_agent.tools`` package object, whose
  names were also module names before feature 018.

Prints each finding and the totals; exits 1 on any finding.
"""

import ast
import importlib
import sys
from pathlib import Path

ROOT = Path.cwd()
GUARDED = {"wcl_agent.cache", "wcl_agent.tools"}
findings: list[str] = []
counts = {"imports": 0, "strings": 0}


def importable(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ModuleNotFoundError:
        return False


def resolve_dotted(path: str) -> str | None:
    """None if ``path`` resolves to a module or module attribute, else the reason."""
    parts = path.split(".")
    for cut in range(len(parts), 0, -1):
        mod = ".".join(parts[:cut])
        if importable(mod):
            obj = importlib.import_module(mod)
            for attr in parts[cut:]:
                if not hasattr(obj, attr):
                    return f"{mod} has no attribute {attr!r}"
                obj = getattr(obj, attr)
            return None
    return "no importable prefix"


def check_from(where: str, module: str, names: list[str]) -> None:
    counts["imports"] += 1
    if not importable(module):
        findings.append(f"{where}: module {module} not found")
        return
    mod = importlib.import_module(module)
    for n in names:
        full = f"{module}.{n}"
        if full in GUARDED:
            findings.append(f"{where}: binds package {full} as a module object")
        elif not (hasattr(mod, n) or (hasattr(mod, "__path__") and importable(full))):
            findings.append(f"{where}: {module} has no {n!r}")


def package_of(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts[:-1])


def scan(path: Path) -> None:
    rel = path.relative_to(ROOT).as_posix()
    tree = ast.parse(path.read_text(), filename=rel)
    for node in ast.walk(tree):
        where = f"{rel}:{getattr(node, 'lineno', '?')}"
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] != "wcl_agent":
                    continue
                counts["imports"] += 1
                if alias.name in GUARDED:
                    findings.append(f"{where}: binds package {alias.name} as a module object")
                elif not importable(alias.name):
                    findings.append(f"{where}: module {alias.name} not found")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if not rel.startswith("wcl_agent/"):
                    continue
                base = package_of(path).split(".")
                base = base[: len(base) - (node.level - 1)]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            if module.split(".")[0] == "wcl_agent":
                check_from(where, module, [a.name for a in node.names])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if value.startswith("wcl_agent.") and " " not in value:
                counts["strings"] += 1
                reason = resolve_dotted(value)
                if reason:
                    findings.append(f"{where}: string {value!r}: {reason}")


sys.path.insert(0, str(ROOT))
files = sorted([*ROOT.joinpath("wcl_agent").rglob("*.py"), *ROOT.joinpath("backend").rglob("*.py"), ROOT / "main.py"])
for f in files:
    if "__pycache__" not in f.parts:
        scan(f)
for line in findings:
    print(line)
print(f"{len(files)} files, {counts['imports']} wcl_agent imports, {counts['strings']} wcl_agent strings, {len(findings)} findings")
sys.exit(1 if findings else 0)
