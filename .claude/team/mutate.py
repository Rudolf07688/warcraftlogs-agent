#!/usr/bin/env python3
"""Prove a test bites: break the guarded code on purpose, run the tests, always restore.

Agent-facing. Exactly one occurrence of OLD is replaced by NEW (or line N by NEW), the tests run
in a clean env, and the file is restored from a backup and checked byte for byte, also on
Ctrl-C or a crash. By default the tests first run unmutated and must pass, so a bite is
really caused by the mutation.

  mutate.py FILE --old "exact text" --new "replacement" --test backend/tests/test_x.py [--test ...]
  mutate.py FILE --line 42 --new "    return True" --test backend/tests/test_x.py::test_name
  options: --pg-url URL (PG tests), --no-baseline

After a crash, a leftover backup sits in .git/team-checks/backups/<file>-*.bak: copy it back.

Exit 0 = BITES (the tests failed under the mutation). Exit 1 = does not bite, or the mutation
only broke import/collection (not a real bite: mutate behaviour, not syntax).
"""
import argparse
import hashlib
import os
import shutil
import signal
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check import checks_dir, env_file_refusal, run_pytest, toplevel  # noqa: E402


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    p = argparse.ArgumentParser(prog="mutate.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--old", help="exact text to replace; must occur exactly once")
    g.add_argument("--line", type=int, help="1-based line number to replace")
    p.add_argument("--new", required=True)
    p.add_argument("--test", action="append", required=True, help="test file or node id (repeatable)")
    p.add_argument("--pg-url")
    p.add_argument("--no-baseline", action="store_true")
    p.add_argument("--allow-env", action="store_true", help="run even though the tree has a .env")
    a = p.parse_args()
    refusal = env_file_refusal(toplevel())
    if refusal and not a.allow_env:
        sys.exit(refusal)

    path = os.path.abspath(a.file)
    src = open(path).read()
    if a.old is not None:
        n = src.count(a.old)
        if n != 1:
            sys.exit(f"mutate: --old occurs {n} times in {a.file}; it must occur exactly once")
        mutated = src.replace(a.old, a.new, 1)
    else:
        lines = src.splitlines(keepends=True)
        if not 1 <= a.line <= len(lines):
            sys.exit(f"mutate: {a.file} has {len(lines)} lines")
        end = "\n" if lines[a.line - 1].endswith("\n") else ""
        lines[a.line - 1] = a.new + end
        mutated = "".join(lines)

    if not a.no_baseline:
        rc, line, counts, log, _ = run_pytest(a.test, a.pg_url, log_name="mutate-baseline")
        if rc or counts.get("failed") or counts.get("errors") or not counts.get("passed"):
            sys.exit(f"mutate: baseline is not green, so a bite would prove nothing: {line or 'no summary'} (log: {log})")

    original = sha(path)
    # in the git common dir, not /tmp: a machine crash mid-run must not take the backup with it
    fd, backup = tempfile.mkstemp(prefix=os.path.basename(path) + "-", suffix=".bak",
                                  dir=checks_dir("backups"))
    os.close(fd)
    shutil.copy2(path, backup)

    done = []

    def restore(*_):
        if done:
            return
        done.append(True)
        shutil.copy2(backup, path)
        if sha(path) != original:
            print(f"mutate: RESTORE MISMATCH for {a.file}; the backup is at {backup}", file=sys.stderr)
            sys.exit(4)
        os.remove(backup)

    def on_signal(signum, frame):
        restore()
        sys.exit(130)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    try:
        open(path, "w").write(mutated)
        rc, line, counts, log, _ = run_pytest(a.test, a.pg_url, log_name="mutate")
    finally:
        restore()

    failed, errors = counts.get("failed", 0), counts.get("errors", 0)
    if failed:
        print(f"BITES: {failed} test(s) failed under the mutation -> {line}\nrestored {a.file} (verified)\nlog: {log}")
        return
    if errors or not line:
        print(f"NOT A REAL BITE: the mutation broke import/collection, not behaviour -> {line or 'no summary'}\n"
              f"restored {a.file} (verified)\nlog: {log}")
        sys.exit(1)
    print(f"DOES NOT BITE: tests still pass with the mutation -> {line}\nrestored {a.file} (verified)\nlog: {log}")
    sys.exit(1)


if __name__ == "__main__":
    main()
