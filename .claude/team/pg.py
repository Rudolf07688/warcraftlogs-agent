#!/usr/bin/env python3
"""Throwaway Postgres for tests: pgvector/pgvector:pg17-trixie on a free port, schema applied.

Agent-facing. One container per NAME (use your board name). Never the compose database.

  pg.py up NAME [--port N] [--no-init]   start (or reuse) it; prints TEST_DATABASE_URL
  pg.py url NAME                         print the URLs of a running one
  pg.py down NAME                        stop it (the container is --rm, so it's gone)
  pg.py ls                               list running team containers

Why this image: plain pg17 is Debian 12, postgres:17 is Debian 13; a database made under one
and opened under the other warns about a collation mismatch. -trixie matches.
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time

IMAGE = "pgvector/pgvector:pg17-trixie"
PREFIX = "wcl-team-pg-"
FIRST_PORT = 15440
OWNER, APP = "wcl:wcl", "wcl_app:wcl_app"


def name_ok(name):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,30}", name):
        sys.exit("pg: NAME must be lowercase letters, digits, - or _ (e.g. your board name)")
    return PREFIX + name


def docker(*args, check=True):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def running_port(container):
    r = docker("port", container, "5432/tcp", check=False)
    m = re.search(r":(\d+)\s*$", r.stdout.strip().splitlines()[0]) if r.returncode == 0 and r.stdout.strip() else None
    return int(m.group(1)) if m else None


def free_port(start):
    taken = set()
    for line in docker("ps", "--format", "{{.Ports}}").stdout.splitlines():
        taken.update(int(p) for p in re.findall(r":(\d+)->", line))
    port = start
    while True:
        if port not in taken:
            with socket.socket() as s:
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    pass
        port += 1


def urls(port):
    return {"port": port,
            "test_url": f"postgresql+asyncpg://{APP}@localhost:{port}/wcl",
            "owner_url": f"postgresql+asyncpg://{OWNER}@localhost:{port}/wcl"}


def top():
    return subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                          check=True).stdout.strip()


def init_db(u):
    env = {"HOME": os.environ["HOME"], "PATH": os.environ["PATH"],
           "APP_DB_USER": "wcl_app", "APP_DB_PASSWORD": "wcl_app",
           "BOOTSTRAP_ADMIN_EMAIL": "founder@example.com",
           "BOOTSTRAP_ADMIN_PASSWORD": "throwaway-founder-pass",
           "DATABASE_OWNER_URL": u["owner_url"], "DATABASE_URL": u["test_url"]}
    r = subprocess.run(["uv", "run", "python", "-m", "backend.cli.init_db"], env=env, cwd=top(),
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit("pg: init_db failed:\n" + (r.stdout + r.stderr)[-2000:])


def ensure(name, port=None, init=True):
    """Start or reuse container NAME; return its URLs. Importable (check.py --pg)."""
    container = name_ok(name)
    existing = running_port(container)
    if existing:
        return urls(existing)
    port = port or free_port(FIRST_PORT)
    docker("run", "-d", "--rm", "--name", container, "-e", "POSTGRES_USER=wcl",
           "-e", "POSTGRES_PASSWORD=wcl", "-e", "POSTGRES_DB=wcl",
           "-p", f"127.0.0.1:{port}:5432", IMAGE)
    # TCP only answers once the init phase (unix socket only) is over
    for _ in range(120):
        if docker("exec", container, "pg_isready", "-h", "127.0.0.1", "-U", "wcl", "-d", "wcl",
                  check=False).returncode == 0:
            break
        time.sleep(0.5)
    else:
        docker("stop", container, check=False)
        sys.exit("pg: Postgres did not become ready in 60 s; container stopped")
    u = urls(port)
    if init:
        init_db(u)
    return u


def cmd_up(a):
    u = ensure(a.name, a.port, not a.no_init)
    print(f"TEST_DATABASE_URL={u['test_url']}\nDATABASE_OWNER_URL={u['owner_url']}\n"
          f"(stop it with: pg.py down {a.name})")


def cmd_url(a):
    port = running_port(name_ok(a.name))
    if not port:
        sys.exit(f"pg: {a.name} is not running")
    u = urls(port)
    print(f"TEST_DATABASE_URL={u['test_url']}\nDATABASE_OWNER_URL={u['owner_url']}")


def cmd_down(a):
    r = docker("stop", name_ok(a.name), check=False)
    print(f"pg: stopped {a.name}" if r.returncode == 0 else f"pg: {a.name} was not running")


def cmd_ls(a):
    rows = docker("ps", "--filter", f"name={PREFIX}", "--format", "{{.Names}} {{.Ports}} {{.RunningFor}}").stdout
    print(rows.strip().replace(PREFIX, "") or "pg: none running")


def main():
    p = argparse.ArgumentParser(prog="pg.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("up")
    q.add_argument("name")
    q.add_argument("--port", type=int)
    q.add_argument("--no-init", action="store_true", help="skip backend.cli.init_db")
    for n in ("url", "down"):
        s.add_parser(n).add_argument("name")
    s.add_parser("ls")
    a = p.parse_args()
    {"up": cmd_up, "url": cmd_url, "down": cmd_down, "ls": cmd_ls}[a.cmd](a)


if __name__ == "__main__":
    main()
