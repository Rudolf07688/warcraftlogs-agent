#!/usr/bin/env python3
"""Job waiter: run a long command detached, then wait for it cheaply (warm-cache ticks).

Agent-facing. A sub-agent's prompt cache lives 5 minutes, so waking cold after a long job
costs about 15x a warm wake. Same design as `board.py wait --warm`: the wait gives up every
270 s with exit 3 and the agent re-runs the identical command; past --warm-for minutes (from
the job's start) it exits 2, because a cold wake is then cheaper than more ticks.

  jobwait.py start NAME -- CMD...   run CMD detached (own session, caller's cwd); stdout+stderr
                                    to <jobs dir>/NAME.log, exit status to NAME.exit; prints the
                                    log path and returns. Refuses while NAME is still running.
  jobwait.py wait NAME [--warm] [--warm-for MIN] [--timeout S] [--tail N] [--grep REGEX]
                                    block until the job ends, print the last N log lines (15)
                                    plus lines matching REGEX. Run it with run_in_background.
  jobwait.py status [NAME]          name, state (running / exit N / lost), age, log path
  jobwait.py clean [NAME]           remove finished jobs' files (running ones are kept)

Jobs live in <git common dir>/team-jobs/<worktree>/, so worktrees share no names. TEAM_JOBS_DIR
overrides the directory (tests). Exit codes of `wait`:
  0 job exited 0     1 job failed, was lost (process gone, no exit file) or is unknown
  2 warm window over (re-arm without --warm) or --timeout reached
  3 warm tick (re-run the identical command)
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

WARM_TICK = int(os.environ.get("JOBWAIT_TICK", "270"))  # seconds; under the 5-minute cache
WARM_FOR_DEFAULT = 25.0                                  # minutes, as in board.py
POLL = float(os.environ.get("JOBWAIT_POLL", "1"))


def jobs_dir():
    override = os.environ.get("TEAM_JOBS_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    try:
        git = lambda *a: subprocess.run(["git", "rev-parse", "--path-format=absolute", *a],
                                        capture_output=True, text=True, check=True).stdout.strip()
        common, top = git("--git-common-dir"), git("--show-toplevel")
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("jobwait: not inside a git repository")
    key = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(top)) + "-" + \
        hashlib.sha1(top.encode()).hexdigest()[:8]
    path = os.path.join(common, "team-jobs", key)
    os.makedirs(path, exist_ok=True)
    return path


def p(d, name, ext):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        sys.exit(f"jobwait: bad job name {name!r} (letters, digits, . _ -)")
    return os.path.join(d, f"{name}.{ext}")


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # a zombie is not running
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True


def meta(d, name):
    try:
        with open(p(d, name, "json")) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def state(d, name):
    """('exit', N) | ('running', None) | ('lost', None) | ('unknown', None)."""
    try:
        with open(p(d, name, "exit")) as f:
            return "exit", int(f.read().strip())
    except FileNotFoundError:
        pass
    except ValueError:
        return "lost", None
    m = meta(d, name)
    if m is None:
        return "unknown", None
    if alive(m["pid"]):
        return "running", None
    if os.path.exists(p(d, name, "exit")):  # raced: exit file landed as the process ended
        return state(d, name)
    return "lost", None


WRAP = 'f="$1"; shift; "$@"; rc=$?; echo $rc > "$f.tmp" && mv "$f.tmp" "$f"'


def cmd_start(a):
    d = jobs_dir()
    if not a.cmd:
        sys.exit("jobwait: start NAME -- CMD...")
    if state(d, a.name)[0] == "running":
        sys.exit(f"jobwait: job {a.name} is still running (jobwait.py status {a.name})")
    for ext in ("exit", "exit.tmp", "log", "json"):
        try:
            os.remove(p(d, a.name, ext))
        except FileNotFoundError:
            pass
    log = p(d, a.name, "log")
    with open(log, "wb") as out:
        proc = subprocess.Popen(["sh", "-c", WRAP, "sh", p(d, a.name, "exit"), *a.cmd],
                                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True)
    tmp = p(d, a.name, "json") + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"pid": proc.pid, "started": time.time(), "cwd": os.getcwd(), "cmd": a.cmd}, f)
    os.replace(tmp, p(d, a.name, "json"))
    print(log)


def report(d, name, a, st, code):
    log = p(d, name, "log")
    try:
        with open(log, errors="replace") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []
    if a.tail > 0:
        print("\n".join(lines[-a.tail:]))
    if a.grep:
        rx = re.compile(a.grep)
        hits = [ln for ln in lines[:-a.tail] if rx.search(ln)] if a.tail > 0 else \
            [ln for ln in lines if rx.search(ln)]
        if hits:
            print(f"--- lines matching {a.grep}")
            print("\n".join(hits))
    if st == "exit" and code == 0:
        print(f"jobwait: {name} exited 0 ({log})")
        sys.exit(0)
    if st == "exit":
        print(f"jobwait: {name} FAILED with exit {code} ({log})")
    else:
        print(f"jobwait: {name} lost: process gone and no exit status (killed or machine "
              f"restarted); partial log {log}")
    sys.exit(1)


def cmd_wait(a):
    d = jobs_dir()
    m = meta(d, a.name)
    if m is None and state(d, a.name)[0] == "unknown":
        sys.exit(f"jobwait: no job {a.name} (jobwait.py status)")
    started = m["started"] if m else time.time()
    timeout = min(a.timeout, WARM_TICK) if a.timeout and a.warm else \
        (WARM_TICK if a.warm else a.timeout)
    deadline = time.monotonic() + timeout if timeout else None
    while True:
        st, code = state(d, a.name)
        if st in ("exit", "lost"):
            report(d, a.name, a, st, code)
        if st == "unknown":
            sys.exit(f"jobwait: job {a.name} vanished (cleaned?)")
        if deadline and time.monotonic() >= deadline:
            break
        time.sleep(POLL)
    waited = (time.time() - started) / 60
    if not a.warm:
        print(f"jobwait: {a.name} still running after {timeout}s ({waited:.0f} min since start); "
              "re-arm or check the job")
        sys.exit(2)
    if waited >= a.warm_for:
        print(f"jobwait: {a.name} still running after {waited:.0f} min; warm window over; "
              "re-arm without --warm.")
        sys.exit(2)
    print(f"jobwait: warm tick ({waited:.0f} min); re-run the identical command in the "
          "background and end your turn; nothing else.")
    sys.exit(3)


def age(sec):
    sec = int(sec)
    return f"{sec // 3600}h{sec % 3600 // 60:02d}m" if sec >= 3600 else \
        f"{sec // 60}m{sec % 60:02d}s"


def names(d, only):
    if only:
        return [only]
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))


def cmd_status(a):
    d = jobs_dir()
    rows = []
    for n in names(d, a.name):
        st, code = state(d, n)
        m = meta(d, n)
        label = f"exit {code}" if st == "exit" else st
        rows.append((n, label, age(time.time() - m["started"]) if m else "-", p(d, n, "log")))
    if not rows:
        print("jobwait: no jobs")
    for r in rows:
        print("  ".join(r))


def cmd_clean(a):
    d = jobs_dir()
    for n in names(d, a.name):
        if state(d, n)[0] == "running":
            print(f"jobwait: {n} still running, kept")
            continue
        for ext in ("exit", "exit.tmp", "log", "json"):
            try:
                os.remove(p(d, n, ext))
            except FileNotFoundError:
                pass
        print(f"jobwait: removed {n}")


def main():
    ap = argparse.ArgumentParser(prog="jobwait.py")
    sub = ap.add_subparsers(dest="cmd_", required=True)
    s = sub.add_parser("start")
    s.add_argument("name")
    s.add_argument("cmd", nargs=argparse.REMAINDER)
    w = sub.add_parser("wait")
    w.add_argument("name")
    w.add_argument("--warm", action="store_true",
                   help=f"give up after {WARM_TICK}s with exit 3; re-run the identical command")
    w.add_argument("--warm-for", type=float, default=WARM_FOR_DEFAULT,
                   help="minutes since job start after which warm ticks stop (exit 2)")
    w.add_argument("--timeout", type=float, default=0, help="plain wait: give up (exit 2) after S")
    w.add_argument("--tail", type=int, default=15)
    w.add_argument("--grep")
    for n in ("status", "clean"):
        sub.add_parser(n).add_argument("name", nargs="?")
    a = ap.parse_args()
    if a.cmd_ == "start" and a.cmd[:1] == ["--"]:
        a.cmd = a.cmd[1:]
    {"start": cmd_start, "wait": cmd_wait, "status": cmd_status, "clean": cmd_clean}[a.cmd_](a)


if __name__ == "__main__":
    main()
