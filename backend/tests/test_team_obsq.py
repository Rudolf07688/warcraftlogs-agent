"""obsq.py (.claude/team/obsq.py, sc-537): read-only Tempo/Loki queries through Grafana's proxy.

A fake Grafana on a free loopback port records every request; obsq.py runs as a subprocess in a
cleared environment, as an agent would run it.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

OBSQ = Path(__file__).resolve().parents[2] / ".claude" / "team" / "obsq.py"
SECRET = "s3cret-pw-4242"

LOKI = {"status": "success", "data": {"resultType": "streams", "result": [
    {"stream": {"service_name": "backend", "level": "info", "pod": "x"},
     "values": [["1794072000000000000", "second line"], ["1794071999000000000", "first line"]]}]}}
SEARCH = {"traces": [{"traceID": "abc123", "rootServiceName": "backend", "rootTraceName": "POST /chat",
                      "startTimeUnixNano": "1794072000000000000", "durationMs": 812}]}
TRACE = {"batches": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "backend"}}]},
                      "scopeSpans": [{"spans": [
                          {"spanId": "AA==", "name": "POST /chat", "startTimeUnixNano": "1000000000",
                           "endTimeUnixNano": "1812000000"},
                          {"spanId": "AB==", "parentSpanId": "AA==", "name": "call_llm",
                           "startTimeUnixNano": "1100000000", "endTimeUnixNano": "1700000000",
                           "status": {"code": 2},
                           "attributes": [{"key": "gen_ai.request.model", "value": {"stringValue": "m1"}}]}]}]}]}


class FakeGrafana(BaseHTTPRequestHandler):
    seen: list[tuple[str, str, str | None]] = []

    def log_message(self, *args) -> None:
        pass

    def _record(self) -> None:
        self.seen.append((self.command, self.path, self.headers.get("Authorization")))

    def do_GET(self) -> None:
        self._record()
        path = self.path.split("?")[0]
        if path.endswith("/redirect"):
            self.send_response(302)
            self.send_header("Location", "/api/admin/users")
            self.end_headers()
            return
        if path.endswith("/echo-auth"):  # worst case: an error body that echoes the credentials
            body = json.dumps({"message": f"denied for {self.headers.get('Authorization')}"}).encode()
            self.send_response(403)
        else:
            body = json.dumps(LOKI if "query_range" in path else SEARCH if path.endswith("/api/search")
                              else TRACE if "/api/traces/" in path else {"ok": True}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_PUT = do_DELETE = do_PATCH = _record


@pytest.fixture
def grafana():
    FakeGrafana.seen = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeGrafana)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def obsq(*args: str, cwd: Path | None = None, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(OBSQ), *args], cwd=cwd,
                          env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/"), **env},
                          capture_output=True, text=True, timeout=60)


def test_every_command_sends_only_gets_to_the_datasource_proxy(grafana: int) -> None:
    env = {"GRAFANA_PORT": str(grafana)}
    for args in (("loki", '{service_name="backend"}'), ("traces", "{}"), ("trace", "abc123"),
                 ("get", "mimir", "api/v1/query", "query=up")):
        r = obsq(*args, **env)
        assert r.returncode == 0, r.stderr
    assert len(FakeGrafana.seen) == 4
    assert all(m == "GET" and p.startswith("/api/datasources/proxy/uid/") for m, p, _ in FakeGrafana.seen)


def test_paths_that_leave_the_proxy_are_refused_before_any_request(grafana: int) -> None:
    for path in ("../../admin/users", "/api/admin/users", "api/x?y=1", "api/%2e%2e/admin"):
        r = obsq("get", "loki", path, GRAFANA_PORT=str(grafana))
        assert r.returncode != 0 and "bad proxy path" in r.stderr
    assert obsq("get", "lo/ki", "x", GRAFANA_PORT=str(grafana)).returncode != 0
    assert FakeGrafana.seen == []


def test_a_redirect_is_not_followed(grafana: int) -> None:
    r = obsq("get", "loki", "redirect", GRAFANA_PORT=str(grafana))
    assert r.returncode != 0
    assert [p for _, p, _ in FakeGrafana.seen] == ["/api/datasources/proxy/uid/loki/redirect"]


def test_credentials_are_sent_but_never_printed(grafana: int) -> None:
    expected = "Basic " + base64.b64encode(f"admin:{SECRET}".encode()).decode()
    for env in ({"GRAFANA_URL": f"http://admin:{SECRET}@127.0.0.1:{grafana}"},
                {"GRAFANA_PORT": str(grafana), "GRAFANA_ADMIN_PASSWORD": SECRET}):
        ok = obsq("traces", "{}", **env)
        bad = obsq("get", "loki", "echo-auth", **env)
        assert ok.returncode == 0 and bad.returncode != 0 and "HTTP 403" in bad.stderr
        for out in (ok.stdout, ok.stderr, bad.stdout, bad.stderr):
            assert SECRET not in out and expected.split()[1] not in out
    assert {a for _, _, a in FakeGrafana.seen} == {expected}


def test_stack_env_file_gives_the_port_and_dotenv_is_never_read(tmp_path: Path, grafana: int) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".env").write_text(f"GRAFANA_PORT={grafana}\nGRAFANA_URL=http://127.0.0.1:{grafana}\n")
    assert "say where Grafana is" in obsq("traces", "{}", cwd=tmp_path).stderr
    stacks = tmp_path / ".git" / "team-stack"
    stacks.mkdir()
    (stacks / "nils.env").write_text(f"export COMPOSE_PROJECT=wcl-obs-nils\nexport GRAFANA_PORT={grafana}\n")
    r = obsq("--stack", "nils", "traces", "{}", cwd=tmp_path)
    assert r.returncode == 0 and "abc123" in r.stdout
    assert obsq("--stack", "../.env", "traces", "{}", cwd=tmp_path).returncode != 0


def test_output_is_compact_and_ordered(grafana: int) -> None:
    env = {"GRAFANA_PORT": str(grafana)}
    loki = obsq("loki", '{service_name="backend"}', **env).stdout.splitlines()
    assert loki[0].endswith("{level=info,service_name=backend} first line") and "second line" in loki[1]
    tree = obsq("trace", "abc123", "--attrs", **env).stdout
    assert "backend: POST /chat" in tree and "  backend: call_llm ERROR" in tree
    assert "gen_ai.request.model=m1" in tree and "600.0 ms" in tree
