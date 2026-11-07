#!/usr/bin/env python3
"""Your own observability stack on free ports, with the env file the stack scripts read.

Agent-facing. One compose project per NAME (use your board name): wcl-obs-NAME. Never the
owner's project, never compose's default ports, never a .env (compose gets --env-file).
up and down refuse in a checkout with a .env: compose would read it through backend's and
db's env_file even when those services aren't selected. Run them from a worktree without one.

  stack.py env NAME [--new]                 pick free ports, write the env file, print its path
  stack.py up NAME [--services S ...]       env, then compose up -d --wait (default services:
                                            alloy loki tempo mimir grafana, as lib.sh stack_up)
  stack.py down NAME                        compose down -v (containers, network, volumes), then
                                            remove the env file and the stack's board dir

The env file lives in $(git rev-parse --git-common-dir)/team-stack/NAME.env, so every worktree
finds it and git never sees it. Its lines are `export KEY=value`: source it in the SAME Bash
call as a stack script (each tool call is a fresh shell):

  source "$(python3 .claude/team/stack.py env ansel)" && bash observability/test/faro.sh

Ports: chosen by a bind check on 127.0.0.1 and 0.0.0.0, skipping ports Docker publishes and
ports in other team-stack env files, all distinct, from 25000-32767 (below the ephemeral range,
above lib.sh's 24xxx defaults). APP_PORT is a spare one for your own vite or uvicorn; browse.py
defaults to it. An existing env file is reused unless --new. A stack script started on a
stack.py stack removes it at its end (lib.sh stack_down) unless KEEP=1.
"""
import argparse
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PREFIX = "wcl-obs-"
PORT_KEYS = ["ALLOY_OTLP_GRPC_PORT", "ALLOY_OTLP_HTTP_PORT", "ALLOY_UI_PORT", "ALLOY_FARO_PORT",
             "GRAFANA_PORT", "PYROSCOPE_PORT", "DB_PORT", "REDIS_PORT", "APP_PORT"]
FIRST, LAST = 25000, 32767
DEFAULT_SERVICES = ["alloy", "loki", "tempo", "mimir", "grafana"]
LINE = re.compile(r"^(?:export )?([A-Z_][A-Z0-9_]*)=(.*)$")


def no_dotenv():
    """Exit if this checkout has a .env: compose loads every service's env_file, selected or not."""
    if (REPO / ".env").exists():
        sys.exit(f"stack: {REPO} has a .env, which docker compose would read (backend's and db's "
                 "env_file); run stack.py up/down from a worktree without one")


def name_ok(name):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,30}", name):
        sys.exit("stack: NAME must be lowercase letters, digits, - or _ (e.g. your board name)")
    if name == "test":
        sys.exit("stack: 'test' would be wcl-obs-test, lib.sh's default project (team-lead's)")
    return name


def stack_dir():
    common = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True,
                            text=True, check=True).stdout.strip()
    return Path(common).resolve() / "team-stack"


def env_path(name):
    return stack_dir() / f"{name}.env"


def read_env(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        m = LINE.match(line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def compose_default_ports():
    """Host ports docker-compose.yml publishes by default (literal or ${VAR:-N})."""
    text = (REPO / "docker-compose.yml").read_text()
    found = re.findall(r'-\s*"(?:[\d.]+:)?(?:\$\{\w+:-(\d+)\}|(\d+)):\d+"', text)
    return {int(a or b) for a, b in found}


def docker_published():
    try:
        r = subprocess.run(["docker", "ps", "--format", "{{.Ports}}"], capture_output=True,
                           text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {int(p) for p in re.findall(r":(\d+)->", r.stdout)}


def team_ports(skip):
    used = set()
    d = stack_dir()
    for f in d.glob("*.env") if d.is_dir() else []:
        if f.name != skip:
            used |= {int(v) for k, v in read_env(f).items() if k in PORT_KEYS and v.isdigit()}
    return used


def bindable(port):
    for host in ("127.0.0.1", "0.0.0.0"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                return False
    return True


def pick_ports(count, start, avoid):
    """COUNT distinct ports from START upwards (wrapping), none in AVOID, each bindable now."""
    span = LAST - FIRST + 1
    picked = []
    for i in range(span):
        port = FIRST + (start - FIRST + i) % span
        if port not in avoid and port not in picked and bindable(port):
            picked.append(port)
            if len(picked) == count:
                return picked
    sys.exit(f"stack: fewer than {count} free ports in {FIRST}-{LAST}")


def write_env(name, new=False):
    path = env_path(name)
    if path.exists() and not new:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    avoid = compose_default_ports() | docker_published() | team_ports(path.name)
    # A per-name starting point spreads developers out; the bind check decides.
    start = FIRST + int.from_bytes(name.encode(), "big") % (LAST - FIRST)
    ports = dict(zip(PORT_KEYS, pick_ports(len(PORT_KEYS), start, avoid)))
    board = path.parent / f"{name}-board"
    board.mkdir(exist_ok=True)
    values = {
        "COMPOSE_PROJECT": PREFIX + name,
        **{k: str(v) for k, v in ports.items()},
        # A fresh empty dir for Alloy's board tail, never the real board.
        "TEAM_BOARD_DIR": str(board),
        "GRAFANA_ADMIN_PASSWORD": "test-" + secrets.token_hex(12),
        # The app services interpolate these; empty, as in lib.sh (no credentials).
        **{k: "" for k in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
                           "APP_DB_USER", "APP_DB_PASSWORD")},
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(f"# stack.py env for {name}: source it in the same shell as the stack script\n")
        f.writelines(f"export {k}={v}\n" for k, v in values.items())
    return path


def compose(path, *args):
    """docker compose on this worktree's compose file, project and env from PATH only."""
    values = read_env(path)
    env = {k: v for k, v in os.environ.items() if k not in values and k != "COMPOSE_PROJECT_NAME"}
    env.update(values)
    cmd = ["docker", "compose", "--progress", "quiet", "-f", str(REPO / "docker-compose.yml"),
           "--env-file", str(path), "-p", values["COMPOSE_PROJECT"], "--profile", "observability",
           *args]
    return subprocess.run(cmd, cwd=REPO, env=env).returncode


def cmd_env(a):
    print(write_env(name_ok(a.name), a.new))


def cmd_up(a):
    name = name_ok(a.name)
    services = a.services or DEFAULT_SERVICES
    no_dotenv()
    path = write_env(name, a.new)
    rc = compose(path, "up", "-d", "--wait", *services)
    v = read_env(path)
    if rc == 0:
        print(f"up: project {v['COMPOSE_PROJECT']}, Grafana http://127.0.0.1:{v['GRAFANA_PORT']}, "
              f"OTLP http://127.0.0.1:{v['ALLOY_OTLP_HTTP_PORT']}, app port {v['APP_PORT']}")
    print(path)
    return rc


def cmd_down(a):
    name = name_ok(a.name)
    no_dotenv()
    path = env_path(name)
    if not path.exists():
        # Down by name with a throwaway env file, so compose still never reads a .env.
        write_env(name)
    rc = compose(path, "down", "-v", "--remove-orphans")
    if rc == 0:
        path.unlink(missing_ok=True)
        shutil.rmtree(path.parent / f"{name}-board", ignore_errors=True)
        print(f"down: project {PREFIX}{name} and its volumes removed, env file deleted")
    return rc


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd in ("env", "up", "down"):
        s = sub.add_parser(cmd)
        s.add_argument("name")
        if cmd != "down":
            s.add_argument("--new", action="store_true", help="pick fresh ports even if the env file exists")
    sub.choices["up"].add_argument("--services", nargs="+", help=f"default: {' '.join(DEFAULT_SERVICES)}")
    a = p.parse_args(argv)
    return {"env": cmd_env, "up": cmd_up, "down": cmd_down}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
