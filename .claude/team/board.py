#!/usr/bin/env python3
"""Team board: an append-only, chronological message board shared by all agents.

Agent-facing. Entries are numbered; a later entry with the same --key overrides earlier
ones. Storage lives in the git common dir, so every worktree of the repo sees one board.

  board.py post <kind> "text" --as NAME [--key K] [--supersedes N] [--ref R ...]
  board.py read --as NAME          unread entries from others, then marks them read
  board.py current [--key PREFIX]  effective state: latest entry per key + open items
  board.py log [--since N] [--last N] [--key PREFIX]
  board.py wait [--kind K] [--author A] [--key P] [--text P] [--since N] [--timeout S]
                                   block until a match, print it (run_in_background: you
                                   are re-invoked when it exits; costs no tokens meanwhile)
  board.py init NAME | close [--export PATH] | status
  board.py hook                    PostToolUse hook: injects unread entries as context

Kinds: decision change notice question answer handoff merge blocker
"""
import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

KINDS = ("decision", "change", "notice", "question", "answer", "handoff", "merge", "blocker")
HOOK_MAX_ENTRIES = 15
HOOK_MAX_CHARS = 3500


def root():
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    path = os.path.join(common, "team-board")
    os.makedirs(os.path.join(path, "cursors"), exist_ok=True)
    return path


def active(r):
    try:
        name = open(os.path.join(r, "active")).read().strip()
    except FileNotFoundError:
        return None
    return name or None


def board_path(r, name):
    return os.path.join(r, f"{name}.jsonl")


def load(r, name):
    try:
        with open(board_path(r, name)) as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


def cursor_file(r, name, reader):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", reader)
    return os.path.join(r, "cursors", f"{name}--{safe}")


def get_cursor(r, name, reader):
    try:
        return int(open(cursor_file(r, name, reader)).read().strip() or 0)
    except (FileNotFoundError, ValueError):
        return 0


def set_cursor(r, name, reader, value):
    with open(cursor_file(r, name, reader), "w") as f:
        f.write(str(value))


def fmt(e):
    t = e["ts"][11:16] + "Z"
    key = f" [{e['key']}]" if e.get("key") else ""
    sup = f" (supersedes #{e['supersedes']})" if e.get("supersedes") else ""
    refs = f" refs: {', '.join(e['refs'])}" if e.get("refs") else ""
    return f"#{e['id']} {t} {e['author']} {e['kind'].upper()}{key}: {e['text']}{sup}{refs}"


def effective(entries):
    """Latest entry per key, plus un-keyed decisions/blockers/questions not superseded."""
    superseded = {e["supersedes"] for e in entries if e.get("supersedes")}
    latest = {}
    loose = []
    for e in entries:
        if e["id"] in superseded:
            continue
        if e.get("key"):
            latest[e["key"]] = e
        elif e["kind"] in ("decision", "blocker", "question"):
            loose.append(e)
    answered = {e["supersedes"] for e in entries if e["kind"] == "answer" and e.get("supersedes")}
    loose = [e for e in loose if e["id"] not in answered]
    return sorted(list(latest.values()) + loose, key=lambda e: e["id"])


def require_board(r):
    name = active(r) if r else None
    if not name:
        sys.exit("team-board: no active board (team-lead runs `board.py init <name>` at launch)")
    return name


def cmd_post(a, r):
    name = require_board(r)
    if a.kind not in KINDS:
        sys.exit(f"team-board: kind must be one of {', '.join(KINDS)}")
    text = a.text if a.text != "-" else sys.stdin.read().strip()
    with open(board_path(r, name), "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        last = 0
        for line in f:
            if line.strip():
                last = json.loads(line)["id"]
        e = {"id": last + 1, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "author": a.as_, "kind": a.kind, "text": " ".join(text.split())}
        if a.key:
            e["key"] = a.key
        if a.supersedes:
            e["supersedes"] = a.supersedes
        if a.ref:
            e["refs"] = a.ref
        f.write(json.dumps(e) + "\n")
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)
    print(f"posted {fmt(e)}")


def cmd_read(a, r):
    name = require_board(r)
    entries = load(r, name)
    seen = get_cursor(r, name, a.as_)
    new = [e for e in entries if e["id"] > seen and e["author"] != a.as_]
    print("\n".join(fmt(e) for e in new) if new else "team-board: nothing new")
    if entries:
        set_cursor(r, name, a.as_, entries[-1]["id"])


def cmd_current(a, r):
    name = require_board(r)
    rows = [e for e in effective(load(r, name)) if not a.key or (e.get("key") or "").startswith(a.key)]
    print("\n".join(fmt(e) for e in rows) if rows else "team-board: empty")


def cmd_log(a, r):
    name = require_board(r)
    rows = [e for e in load(r, name) if e["id"] > (a.since or 0)
            and (not a.key or (e.get("key") or "").startswith(a.key))]
    if a.last:
        rows = rows[-a.last:]
    print("\n".join(fmt(e) for e in rows) if rows else "team-board: empty")


def matches(e, a):
    return ((not a.kind or e["kind"] in a.kind)
            and (not a.author or e["author"].lower() in [x.lower() for x in a.author])
            and (not a.key or (e.get("key") or "").startswith(a.key))
            and (not a.text or e["text"].startswith(tuple(a.text))))


def cmd_wait(a, r):
    """Block until a matching entry appears, print it, exit 0 (timeout: exit 2). Run it with
    run_in_background: the agent is re-invoked when it exits, at no token cost while waiting."""
    import time
    name = require_board(r)
    entries = load(r, name)
    since = a.since if a.since is not None else (entries[-1]["id"] if entries else 0)
    deadline = time.monotonic() + a.timeout
    while True:
        hits = [e for e in load(r, name) if e["id"] > since and matches(e, a)]
        if hits:
            print("\n".join(fmt(e) for e in hits))
            return
        if time.monotonic() >= deadline:
            print(f"team-board: no match after {a.timeout}s (since #{since}); re-arm or check the agent")
            sys.exit(2)
        time.sleep(a.interval)


def cmd_init(a, r):
    if not r:
        sys.exit("team-board: not inside a git repository")
    open(os.path.join(r, "active"), "w").write(a.name)
    open(board_path(r, a.name), "a").close()
    print(f"team-board: active board is {a.name} ({board_path(r, a.name)})")


def cmd_close(a, r):
    name = require_board(r)
    if a.export:
        os.makedirs(os.path.dirname(os.path.abspath(a.export)), exist_ok=True)
        with open(board_path(r, name)) as src, open(a.export, "w") as dst:
            dst.write(src.read())
        print(f"team-board: exported {name} to {a.export}")
    os.remove(os.path.join(r, "active"))
    print(f"team-board: closed {name}")


def cmd_status(a, r):
    name = active(r) if r else None
    if not name:
        print("team-board: no active board")
        return
    entries = load(r, name)
    print(f"team-board: {name}, {len(entries)} entries, {board_path(r, name)}")


def reader_from_hook(d, r):
    """Resolve who is reading. Named teammates have agent ids like 'adev-a-032-<16 hex>'.
    Unnamed sub-agents ('a<hex>') are learned from the --as of their first board command."""
    aid = d.get("agent_id")
    if not aid:
        return "team-lead"
    alias = os.path.join(r, "cursors", f"alias--{re.sub(r'[^A-Za-z0-9_.-]', '_', aid)}")
    cmd = (d.get("tool_input") or {}).get("command", "") if d.get("tool_name") == "Bash" else ""
    m = re.search(r"board\.py\b.*--as[ =]['\"]?([A-Za-z0-9_.-]+)", cmd)
    if m:
        open(alias, "w").write(m.group(1))
        return m.group(1)
    try:
        return open(alias).read().strip()
    except FileNotFoundError:
        pass
    m = re.fullmatch(r"a(.+)-[0-9a-f]{16}", aid)
    return m.group(1) if m else aid


def cmd_hook(a, r):
    try:
        d = json.load(sys.stdin)
    except ValueError:
        return
    name = active(r) if r else None
    if not name:
        return
    reader = reader_from_hook(d, r)
    entries = load(r, name)
    seen = get_cursor(r, name, reader)
    new = [e for e in entries if e["id"] > seen and e["author"] != reader]
    if entries:
        set_cursor(r, name, reader, entries[-1]["id"])
    if not new:
        return
    shown, size = [], 0
    for e in new[-HOOK_MAX_ENTRIES:]:
        line = fmt(e)
        if size + len(line) > HOOK_MAX_CHARS:
            break
        shown.append(line)
        size += len(line)
    more = len(new) - len(shown)
    head = (f"[team-board] {len(new)} new entr{'y' if len(new) == 1 else 'ies'} for {reader} "
            "(chronological; a later entry on the same key overrides earlier ones):")
    tail = f"\n... {more} older not shown: run `board.py log --since {seen}`" if more else ""
    print(json.dumps({"hookSpecificOutput": {"hookEventName": d.get("hook_event_name", "PostToolUse"),
                                             "additionalContext": head + "\n" + "\n".join(shown) + tail}}))


def main():
    p = argparse.ArgumentParser(prog="board.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("post")
    q.add_argument("kind")
    q.add_argument("text", help='entry text, or "-" to read it from stdin')
    q.add_argument("--as", dest="as_", required=True, help="your agent name, e.g. dev-a-032")
    q.add_argument("--key", help="topic key; the latest entry per key is the effective one")
    q.add_argument("--supersedes", type=int, help="id of the entry this one replaces or answers")
    q.add_argument("--ref", action="append", help="commit, ticket or path (repeatable)")
    q = s.add_parser("read")
    q.add_argument("--as", dest="as_", required=True)
    q = s.add_parser("current")
    q.add_argument("--key")
    q = s.add_parser("log")
    q.add_argument("--since", type=int)
    q.add_argument("--last", type=int)
    q.add_argument("--key")
    q = s.add_parser("wait", help="block until a matching entry appears (run in background)")
    q.add_argument("--kind", action="append", help="entry kind (repeatable)")
    q.add_argument("--author", action="append", help="author name (repeatable)")
    q.add_argument("--key", help="key prefix")
    q.add_argument("--text", action="append", help="text prefix, e.g. ESCALATION (repeatable)")
    q.add_argument("--since", type=int, help="entry id to wait after (default: the latest now)")
    q.add_argument("--timeout", type=int, default=5400, help="seconds (default 5400 = 90 min)")
    q.add_argument("--interval", type=float, default=3.0)
    q = s.add_parser("init")
    q.add_argument("name")
    q = s.add_parser("close")
    q.add_argument("--export")
    s.add_parser("status")
    s.add_parser("hook")
    a = p.parse_args()
    if a.cmd == "hook":
        try:  # a hook must never break the agent's tool call
            cmd_hook(a, root())
        except Exception:
            pass
        return
    r = root()
    {"post": cmd_post, "read": cmd_read, "current": cmd_current, "log": cmd_log, "wait": cmd_wait,
     "init": cmd_init,
     "close": cmd_close, "status": cmd_status, "hook": cmd_hook}[a.cmd](a, r)


if __name__ == "__main__":
    main()
