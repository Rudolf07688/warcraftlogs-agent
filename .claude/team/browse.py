#!/usr/bin/env python3
"""Headless Chrome against your own port: steps, page text and a full-height screenshot.

Agent-facing. Drives /usr/bin/google-chrome over the DevTools protocol (stdlib only, no
browser download). Loopback URLs only, and never a port docker-compose.yml publishes by
default (the owner's app and telemetry). The same rule holds for every request the browser
makes (redirects, scripts, frames, workers, fetches), checked on the URL Chrome reports; a
blocked one is printed to stderr. WebSocket connections are not intercepted.

  browse.py URL [--step S ...] [--text] [--shot PNG] [--width 1600] [--height 900]
  browse.py /path --as NAME ...      URL on 127.0.0.1:APP_PORT from stack.py's env for NAME

Steps run in order after the page has loaded; each waits up to --timeout seconds:
  click:CSS | click:text=Label   click the element's centre (real mouse events)
  type:TEXT                      insert TEXT into the focused element (click it first)
  press:Enter|Tab|Escape|Backspace
  wait:TEXT  /  gone:TEXT        until the page text contains / no longer contains TEXT
  sleep:MS                       pause
  eval:JS                        print the JSON value of a JS expression

--shot grows the window to the tallest scroll height on the page (at least --height) before
the capture, so nothing is off-screen: Grafana leaves panels outside the window blank.
--text prints document.body.innerText after the steps. Console errors and uncaught
exceptions go to stderr. Exit 0 ok, 1 a step failed, 2 refused or Chrome failed.

Example (a chat send):
  browse.py http://127.0.0.1:31544/ --step 'click:textarea' --step 'type:hello' \\
    --step 'press:Enter' --step 'wait:hello' --text --shot /tmp/x/chat.png
"""
import argparse
import base64
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack  # same directory: env files and compose's default ports

CHROME = "/usr/bin/google-chrome"
# Plain scheme://loopback[:port] then path, query, fragment or nothing; printable ASCII, no
# backslash (Chrome reads one as '/', Python doesn't), so no userinfo can shift the host.
SAFE_URL = re.compile(r"(https?)://(?:127\.0\.0\.1|localhost|\[::1\])(?::(\d{1,5}))?(?:[/?#][!-\[\]-~]*)?")
MAX_HEIGHT = 16000
KEYS = {"Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8}


class StepFailed(Exception):
    pass


def refusal(url, default_ports):
    """Why URL may not be loaded, or None if it is plain loopback http(s) on an allowed port."""
    m = SAFE_URL.fullmatch(url)
    if not m:
        return f"refused {url!r}: only plain http(s)://127.0.0.1|localhost|[::1][:port]/..."
    port = int(m.group(2) or (443 if m.group(1) == "https" else 80))
    if port in default_ports:
        return f"refused port {port}: a docker-compose.yml default (the owner's stack)"
    return None


def check_url(url):
    """The URL if refusal() has nothing against it; otherwise exit 2."""
    reason = refusal(url, stack.compose_default_ports())
    if reason:
        sys.exit(f"browse: {reason}")
    return url


class WebSocket:
    """Just enough RFC 6455 for one DevTools page: masked text frames out, frames in."""

    def __init__(self, url):
        u = urlsplit(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
                           f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                           "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1)
            if not chunk:
                raise ConnectionError("DevTools closed the handshake")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head.decode(errors="replace"))

    def _exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("DevTools connection closed")
            buf += chunk
        return buf

    def send(self, text, opcode=0x1):
        data = text.encode() if isinstance(text, str) else text
        n = len(data)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 1 << 16:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        message = b""
        while True:
            b0, b1 = self._exact(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._exact(8))[0]
            mask = self._exact(4) if b1 & 0x80 else None
            data = self._exact(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            opcode = b0 & 0x0F
            if opcode == 0x9:
                self.send(data, 0xA)
                continue
            if opcode == 0x8:
                raise ConnectionError("DevTools closed the connection")
            message += data
            if b0 & 0x80:
                return message.decode()


class Page:
    """The browser connection: browser-wide request guard, page commands on a flat session."""

    def __init__(self, ws):
        self.ws, self.next_id, self.errors, self.session = ws, 0, [], None
        self.default_ports = stack.compose_default_ports()

    def send(self, method, session, **params):
        self.next_id += 1
        msg = {"id": self.next_id, "method": method, "params": params}
        if session:
            msg["sessionId"] = session
        self.ws.send(json.dumps(msg))
        return self.next_id

    def call(self, method, **params):
        """Send to the page session (the browser before attach) and wait for the reply."""
        sent = self.send(method, self.session, **params)
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == sent:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            self._event(msg)

    def _event(self, msg):
        p = msg.get("params", {})
        if msg.get("method") == "Fetch.requestPaused":
            url = p["request"]["url"]
            reason = refusal(url, self.default_ports)
            if reason:
                if not url.startswith("chrome-extension://"):  # Chrome's own, every run
                    print(f"browse: blocked request {url}: {reason}", file=sys.stderr)
                self.send("Fetch.failRequest", msg.get("sessionId"), requestId=p["requestId"],
                          errorReason="BlockedByClient")
            else:
                self.send("Fetch.continueRequest", msg.get("sessionId"), requestId=p["requestId"])
        elif msg.get("method") == "Runtime.exceptionThrown":
            d = p.get("exceptionDetails", {})
            self.errors.append("exception: " + (d.get("exception", {}).get("description") or d.get("text", "")))
        elif msg.get("method") == "Runtime.consoleAPICalled" and p.get("type") == "error":
            self.errors.append("console error: " + " ".join(
                str(a.get("value", a.get("description", ""))) for a in p.get("args", [])))

    def js(self, expression):
        r = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            raise StepFailed(f"JS error in {expression[:60]!r}: {r['exceptionDetails'].get('text')}")
        return r.get("result", {}).get("value")

    def until(self, expression, what, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = self.js(expression)
            if value:
                return value
            time.sleep(0.1)
        raise StepFailed(f"timed out after {timeout:g} s: {what}")


def find_js(target):
    """JS that returns the centre of the element TARGET names, scrolled into view, or null."""
    if target.startswith("text="):
        label = json.dumps(target[5:])
        pick = ("[...document.querySelectorAll('body *')].filter(e => e.innerText && "
                f"e.innerText.includes({label})).pop()")
    else:
        pick = f"document.querySelector({json.dumps(target)})"
    return (f"(() => {{ const e = {pick}; if (!e) return null; e.scrollIntoView({{block: 'center'}}); "
            "const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })()")


def run_step(page, step, timeout):
    kind, _, arg = step.partition(":")
    has_text = f"document.body.innerText.includes({json.dumps(arg)})"
    if kind == "click":
        x, y = page.until(find_js(arg), f"element {arg!r}", timeout)
        for event in ("mousePressed", "mouseReleased"):
            page.call("Input.dispatchMouseEvent", type=event, x=x, y=y, button="left", clickCount=1)
    elif kind == "type":
        page.call("Input.insertText", text=arg)
    elif kind == "press":
        if arg not in KEYS:
            raise StepFailed(f"press: unknown key {arg!r} (known: {', '.join(KEYS)})")
        extra = {"text": "\r"} if arg == "Enter" else {}
        page.call("Input.dispatchKeyEvent", type="keyDown", key=arg, code=arg,
                  windowsVirtualKeyCode=KEYS[arg], **extra)
        page.call("Input.dispatchKeyEvent", type="keyUp", key=arg, code=arg, windowsVirtualKeyCode=KEYS[arg])
    elif kind == "wait":
        page.until(has_text, f"text {arg!r}", timeout)
    elif kind == "gone":
        page.until(f"!{has_text}", f"text {arg!r} to go", timeout)
    elif kind == "sleep":
        time.sleep(int(arg) / 1000)
    elif kind == "eval":
        print(json.dumps(page.js(arg)))
    else:
        raise StepFailed(f"unknown step {step!r}")


PAGE_HEIGHT_JS = ("Math.max(document.documentElement.scrollHeight, "
                  "...[...document.querySelectorAll('*')].map(e => e.scrollHeight))")


def screenshot(page, path, width, min_height):
    """Grow the window until the page's tallest scroll height fits, then capture."""
    height = 0
    for _ in range(4):
        want = min(MAX_HEIGHT, max(min_height, page.js(PAGE_HEIGHT_JS)))
        if want == height:
            break
        height = want
        page.call("Emulation.setDeviceMetricsOverride", width=width, height=height,
                  deviceScaleFactor=1, mobile=False)
        time.sleep(0.5)  # let the layout and lazy panels render at the new size
    data = page.call("Page.captureScreenshot", format="png")["data"]
    Path(path).write_bytes(base64.b64decode(data))
    print(f"shot: {path} {width}x{height}")


def launch(width, height, profile):
    return subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
         "--disable-background-networking", "--disable-component-update", "--disable-sync",
         "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
         "--no-proxy-server", f"--user-data-dir={profile}", "--remote-debugging-port=0",
         f"--window-size={width},{height}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def connect(proc, profile):
    """Page on Chrome's browser endpoint, every request held to refusal() before the page loads."""
    port_file = Path(profile) / "DevToolsActivePort"
    end = time.monotonic() + 30
    while not port_file.exists() or not port_file.read_text().strip():
        if proc.poll() is not None or time.monotonic() > end:
            sys.exit("browse: Chrome did not start")
        time.sleep(0.1)
    base = f"http://127.0.0.1:{int(port_file.read_text().split()[0])}"
    with urllib.request.urlopen(f"{base}/json/version", timeout=10) as r:
        browser_ws = json.load(r)["webSocketDebuggerUrl"]
    with urllib.request.urlopen(f"{base}/json/list", timeout=10) as r:
        target = next(t for t in json.load(r) if t["type"] == "page")
    page = Page(WebSocket(browser_ws))
    # Browser-wide, so out-of-process frames and workers are held to the rule too.
    page.call("Fetch.enable", patterns=[{"urlPattern": "*"}])
    page.session = page.call("Target.attachToTarget", targetId=target["id"], flatten=True)["sessionId"]
    return page


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url")
    p.add_argument("--as", dest="name", help="a /path URL goes to APP_PORT in stack.py's env for NAME")
    p.add_argument("--step", action="append", default=[], help="see above; repeatable, run in order")
    p.add_argument("--text", action="store_true", help="print the page text after the steps")
    p.add_argument("--shot", help="write a full-height PNG screenshot here")
    p.add_argument("--width", type=int, default=1600)
    p.add_argument("--height", type=int, default=900, help="window height; --shot grows it to the page")
    p.add_argument("--timeout", type=float, default=30, help="seconds per step and for the page load")
    a = p.parse_args(argv)
    url = a.url
    if url.startswith("/"):
        if not a.name:
            sys.exit("browse: a /path URL needs --as NAME (stack.py env NAME gives APP_PORT)")
        url = f"http://127.0.0.1:{stack.read_env(stack.env_path(stack.name_ok(a.name)))['APP_PORT']}{url}"
    check_url(url)
    if not os.access(CHROME, os.X_OK):
        sys.exit(f"browse: {CHROME} not found")
    profile = tempfile.mkdtemp(prefix="browse-")
    proc = None
    try:
        proc = launch(a.width, a.height, profile)
        page = connect(proc, profile)
        page.call("Runtime.enable")
        page.call("Page.enable")
        nav = page.call("Page.navigate", url=url)
        status = 0
        try:
            if nav.get("errorText"):
                raise StepFailed(f"cannot load {url}: {nav['errorText']}")
            page.until("location.href !== 'about:blank' && document.readyState === 'complete'",
                       f"page load of {url}", a.timeout)
            for step in a.step:
                run_step(page, step, a.timeout)
        except StepFailed as e:
            print(f"FAIL  {e}", file=sys.stderr)
            status = 1
        if a.text:
            print(page.js("document.body.innerText"))
        if a.shot:
            screenshot(page, a.shot, a.width, a.height)
        page.js("0")  # drain queued console events
        for err in page.errors:
            print(err, file=sys.stderr)
        return status
    finally:
        if proc:
            proc.kill()
            proc.wait()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
