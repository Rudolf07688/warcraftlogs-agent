"""Team stack helper (.claude/team/stack.py): free ports, the env file, and a down that cleans up."""
from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

STACK = Path(__file__).resolve().parents[2] / ".claude" / "team" / "stack.py"


def _module():
    spec = importlib.util.spec_from_file_location("team_stack", STACK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(STACK), *args], cwd=cwd, capture_output=True,
                          text=True, timeout=300)


def test_a_busy_port_is_never_picked(repo: Path, monkeypatch) -> None:
    stack = _module()
    monkeypatch.chdir(repo)
    port = stack.pick_ports(1, stack.FIRST, set())[0]
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", port))
        busy.listen()
        assert port not in stack.pick_ports(3, port, set())


def test_env_writes_free_distinct_ports_off_the_defaults_where_git_never_sees_them(repo: Path) -> None:
    stack = _module()
    paths = [Path(run(repo, "env", name).stdout.strip()) for name in ("alpha", "beta")]
    envs = [stack.read_env(p) for p in paths]
    ports = [int(v) for env in envs for k, v in env.items() if k in stack.PORT_KEYS]
    assert len(ports) == 2 * len(stack.PORT_KEYS) and len(set(ports)) == len(ports)
    assert not set(ports) & stack.compose_default_ports()
    assert all(stack.FIRST <= p <= stack.LAST and stack.bindable(p) for p in ports)
    assert [e["COMPOSE_PROJECT"] for e in envs] == ["wcl-obs-alpha", "wcl-obs-beta"]
    for p in paths:
        assert p.parent == (repo / ".git" / "team-stack").resolve()
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True,
                          text=True).stdout == ""
    assert run(repo, "env", "alpha").stdout.strip() == str(paths[0])  # reused, not re-picked
    assert stack.read_env(paths[0]) == envs[0]


def test_lib_sh_default_project_is_refused(repo: Path) -> None:
    r = run(repo, "env", "test")
    assert r.returncode != 0 and "wcl-obs-test" in r.stderr
    assert not (repo / ".git" / "team-stack" / "test.env").exists()


def _docker_has(image: str) -> bool:
    if not shutil.which("docker"):
        return False
    r = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
    return r.returncode == 0


def _project_objects(project: str) -> list[str]:
    label = f"label=com.docker.compose.project={project}"
    out = []
    for what in (["ps", "-aq"], ["volume", "ls", "-q"], ["network", "ls", "-q"]):
        r = subprocess.run(["docker", *what, "--filter", label], capture_output=True, text=True)
        out += r.stdout.split()
    return out


@pytest.mark.skipif(not _docker_has("grafana/loki:3.7.9"), reason="needs Docker and the Loki image")
def test_up_starts_the_project_and_down_removes_it(repo: Path) -> None:
    name = f"t{uuid.uuid4().hex[:8]}"
    project = f"wcl-obs-{name}"
    try:
        up = run(repo, "up", name, "--services", "loki")
        assert up.returncode == 0, up.stderr
        assert _project_objects(project)
        down = run(repo, "down", name)
        assert down.returncode == 0, down.stderr
        assert _project_objects(project) == []
        assert not (repo / ".git" / "team-stack" / f"{name}.env").exists()
    finally:
        if _project_objects(project):
            subprocess.run(["docker", "compose", "-p", project, "down", "-v"], capture_output=True,
                           env={**os.environ})
