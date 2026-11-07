"""Team headless browser (.claude/team/browse.py): loopback only, steps, text, full-height shot."""
from __future__ import annotations

import http.server
import os
import struct
import subprocess
import sys
import threading
from pathlib import Path

import pytest

BROWSE = Path(__file__).resolve().parents[2] / ".claude" / "team" / "browse.py"
CHROME = "/usr/bin/google-chrome"
PAGE = b"""<!doctype html><html><body style="margin:0">
<input id="q"><button onclick="document.getElementById('out').textContent='sent:'+q.value">Send</button>
<p id="out"></p><div style="height:3000px"></div><p>bottom marker</p>
<script>q.addEventListener('keydown', e => { if (e.key === 'Enter') out.textContent = 'enter:' + q.value })</script>
</body></html>"""


def browse(*args: str, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BROWSE), *args], capture_output=True, text=True,
                          timeout=timeout)


@pytest.mark.parametrize("url", ["http://example.com/", "http://127.0.0.1:8000/",
                                 "http://localhost:3000/", "file:///etc/passwd"])
def test_refuses_anything_but_a_loopback_url_on_a_non_default_port(url: str) -> None:
    r = browse(url)
    assert r.returncode != 0 and "refused" in r.stderr


@pytest.fixture
def site():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


@pytest.mark.skipif(not os.access(CHROME, os.X_OK), reason="needs /usr/bin/google-chrome")
def test_steps_drive_the_page_and_the_shot_covers_the_whole_page(site: str, tmp_path: Path) -> None:
    shot = tmp_path / "page.png"
    r = browse(site, "--step", "click:#q", "--step", "type:hi", "--step", "press:Enter",
               "--step", "wait:enter:hi", "--step", "click:text=Send", "--step", "wait:sent:hi",
               "--text", "--shot", str(shot), "--height", "600")
    assert r.returncode == 0, r.stderr
    assert "sent:hi" in r.stdout and "bottom marker" in r.stdout
    png = shot.read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", png[16:24])
    assert width == 1600 and height > 3000


@pytest.mark.skipif(not os.access(CHROME, os.X_OK), reason="needs /usr/bin/google-chrome")
def test_a_wait_that_never_comes_fails_with_exit_1(site: str) -> None:
    r = browse(site, "--step", "wait:never shown", "--timeout", "2")
    assert r.returncode == 1 and "timed out" in r.stderr
