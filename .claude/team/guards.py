#!/usr/bin/env python3
"""List the architecture guard tests: tests that scan the source tree and pin a rule such as
"only provider.py may build model clients". Run it before a plan gate; a plan that moves code
across one of these lines fails them.

  guards.py            every guard: file::test, then its docstring or its name as a sentence
  guards.py WORD       only guards whose name, docstring or body mentions WORD (e.g. RawFetch)

Found by reading the tests, so the list never goes stale: a test counts as a guard when its
body walks or reads source files (rglob, os.walk, glob, read_text) of app code (*.py,
backend/app, wcl_agent), directly or through a helper in the same module.
"""
import ast
import os
import re
import subprocess
import sys

MARKERS = (".rglob(", "os.walk(", ".glob(", "glob.glob(", ".read_text(", "inspect.getsource(")
CODE_SIGNS = ("*.py", '".py"', "'.py'", "backend/app", "wcl_agent", '"app"', "'app'", "getsource(")
TEST_DIRS = ("backend/tests", "wcl_agent/tests", "tests")


def scans_code(text):
    return any(m in text for m in MARKERS) and any(c in text for c in CODE_SIGNS)


def top():
    return subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                          check=True).stdout.strip()


def helpers_that_scan(tree, src):
    """Module-level helper functions that scan files; a test calling one is a guard too."""
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("test_")
            and scans_code(ast.get_source_segment(src, n) or "")}


def guards(root):
    for d in TEST_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, _, files in os.walk(base):
            for f in sorted(files):
                if not (f.startswith("test_") and f.endswith(".py")):
                    continue
                path = os.path.join(dirpath, f)
                src = open(path).read()
                try:
                    tree = ast.parse(src)
                except SyntaxError:
                    continue
                scanners = helpers_that_scan(tree, src)
                for n in ast.walk(tree):
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_"):
                        body = ast.get_source_segment(src, n) or ""
                        called = {c.func.id for c in ast.walk(n) if isinstance(c, ast.Call)
                                  and isinstance(c.func, ast.Name)}
                        if scans_code(body) or called & scanners:
                            doc = (ast.get_docstring(n) or "").strip().splitlines()
                            yield os.path.relpath(path, root), n.name, (doc[0] if doc else ""), body


def main():
    word = sys.argv[1].lower() if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    rows = [r for r in guards(top()) if not word or word in (r[1] + r[2] + r[3]).lower()]
    last = None
    for path, name, doc, _ in rows:
        if path != last:
            print(path)
            last = path
        sentence = doc or re.sub(r"^test_", "", name).replace("_", " ")
        print(f"  {name}: {sentence}")
    print(f"\n{len(rows)} guard test(s){' mentioning ' + word if word else ''}. "
          "Read the test before planning around it.")


if __name__ == "__main__":
    main()
