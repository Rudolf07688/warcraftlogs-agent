#!/usr/bin/env python3
"""Read-only Tempo/Loki query helper through a Grafana datasource proxy (sc-537).

Agent-facing. Every request is an HTTP GET to <grafana>/api/datasources/proxy/uid/<uid>/<path>;
nothing else can be sent (one fetch function, method fixed, redirects refused).

  obsq.py [--stack NAME] loki 'LOGQL' [--since 1h] [--limit 50] [--width 400]
  obsq.py [--stack NAME] traces 'TRACEQL' [--since 1h] [--limit 20]    Tempo search
  obsq.py [--stack NAME] trace TRACE_ID [--attrs]                     one trace as a span tree
  obsq.py [--stack NAME] get UID PATH [key=value ...]                 any GET, JSON out (Mimir too)

Where Grafana is, first match wins:
  --stack NAME   your own test stack: GRAFANA_PORT from stack.py's env file
                 (<git common dir>/team-stack/NAME.env, contract:stack-env)
  GRAFANA_URL    e.g. http://127.0.0.1:27000 (user:password@ in it is used, never printed)
  GRAFANA_PORT   http://127.0.0.1:$GRAFANA_PORT, as observability/test/lib.sh sets it
Credentials are optional (the test stacks let anonymous Viewers query): GRAFANA_USER (default
admin) and GRAFANA_PASSWORD or GRAFANA_ADMIN_PASSWORD from the environment. The tool never
reads an .env file and never prints a credential. The owner's stack is team-lead's: ask with a
live-check: question rather than pointing this at it.
Datasource uids: --loki-uid / --tempo-uid (default loki, tempo, as provisioned).
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PROXY = "/api/datasources/proxy/uid/"
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


OPENER = urllib.request.build_opener(NoRedirect)


def die(msg):
    sys.exit(f"obsq: {msg}")


def stack_env(name):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        die("--stack takes a stack.py name (lower case, digits, '-')")
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True).stdout.strip()
    path = os.path.join(common, "team-stack", f"{name}.env")
    try:
        text = open(path).read()
    except OSError:
        die(f"no env file for stack {name!r} ({path}); run `stack.py up {name}` first")
    return dict(re.findall(r"^(?:export\s+)?([A-Z_][A-Z0-9_]*)=['\"]?([^'\"\n]*)", text, re.M))


def target(a):
    """(base URL without credentials, (user, password) or None)."""
    env = os.environ
    if a.stack:
        port, url = stack_env(a.stack).get("GRAFANA_PORT"), None
        if not port:
            die(f"stack {a.stack!r} has no GRAFANA_PORT in its env file")
    else:
        url, port = env.get("GRAFANA_URL"), env.get("GRAFANA_PORT")
    if not url:
        if not port or not port.isdigit():
            die("say where Grafana is: --stack NAME, GRAFANA_URL or GRAFANA_PORT")
        url = f"http://127.0.0.1:{port}"
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        die("GRAFANA_URL must be an http(s) URL")
    user, password = u.username, u.password
    netloc = u.hostname + (f":{u.port}" if u.port else "")
    base = urllib.parse.urlunsplit((u.scheme, netloc, u.path.rstrip("/"), "", ""))
    password = password or env.get("GRAFANA_PASSWORD") or env.get("GRAFANA_ADMIN_PASSWORD")
    if password:
        return base, (urllib.parse.unquote(user or env.get("GRAFANA_USER", "admin")),
                      urllib.parse.unquote(password))
    return base, None


def scrub(text, auth):
    if auth:
        for secret in {auth[1], base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()}:
            text = text.replace(secret, "***")
    return text


def get(base, auth, uid, path, params=None):
    """The only way out: a GET to the datasource proxy. Returns the parsed JSON body."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", uid):
        die(f"bad datasource uid {uid!r}")
    if path.startswith("/") or any(c in path for c in "?#\\") or ".." in path.split("/") \
            or "%" in path:
        die(f"bad proxy path {path!r}: relative, no '..', no query (pass key=value instead)")
    url = base + PROXY + uid + "/" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    if auth:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    try:
        with OPENER.open(req, timeout=30) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace") if e.fp else ""
        die(scrub(f"HTTP {e.code} {e.reason} for {uid}/{path}: {detail}", auth))
    except (urllib.error.URLError, OSError) as e:
        die(scrub(f"cannot reach Grafana at {base}: {getattr(e, 'reason', e)}", auth))
    try:
        return json.loads(body)
    except ValueError:
        die(scrub(f"non-JSON answer from {uid}/{path}: {body[:200]!r}", auth))


def since_seconds(text):
    m = re.fullmatch(r"(\d+)([smhd])", text)
    if not m:
        die(f"--since takes e.g. 30m, 2h, 1d (got {text!r})")
    return int(m.group(1)) * UNITS[m.group(2)]


def iso(ns):
    return datetime.fromtimestamp(int(ns) / 1e9, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def cmd_loki(a, base, auth):
    end = time.time_ns()
    data = get(base, auth, a.loki_uid, "loki/api/v1/query_range",
               {"query": a.query, "start": end - since_seconds(a.since) * 10**9, "end": end,
                "limit": a.limit, "direction": "backward"})
    if a.json:
        return print(json.dumps(data, indent=1))
    rows = []
    for stream in (data.get("data") or {}).get("result") or []:
        labels = stream.get("stream") or stream.get("metric") or {}
        tag = ",".join(f"{k}={v}" for k, v in sorted(labels.items()) if k in a.labels)
        for ts, line in stream.get("values") or []:
            rows.append((int(ts), tag, line))
    for ts, tag, line in sorted(rows):
        line = line if len(line) <= a.width else line[:a.width] + f"... (+{len(line) - a.width})"
        print(f"{iso(ts)} {{{tag}}} {line}")
    print(f"obsq: {len(rows)} line(s)", file=sys.stderr)


def cmd_traces(a, base, auth):
    end = int(time.time())
    data = get(base, auth, a.tempo_uid, "api/search",
               {"q": a.query, "start": end - since_seconds(a.since), "end": end, "limit": a.limit})
    if a.json:
        return print(json.dumps(data, indent=1))
    traces = data.get("traces") or []
    for t in traces:
        print(f"{t.get('traceID')}  {iso(t.get('startTimeUnixNano', 0))}  "
              f"{t.get('durationMs', '?')} ms  {t.get('rootServiceName', '?')}: {t.get('rootTraceName', '?')}")
    print(f"obsq: {len(traces)} trace(s)", file=sys.stderr)


def attr_value(v):
    for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if k in v:
            return v[k]
    return json.dumps(v)


def cmd_trace(a, base, auth):
    if not re.fullmatch(r"[0-9a-fA-F]{1,32}", a.trace_id):
        die("trace id: up to 32 hex characters")
    data = get(base, auth, a.tempo_uid, f"api/traces/{a.trace_id}")
    if a.json:
        return print(json.dumps(data, indent=1))
    spans = []
    for rs in data.get("batches") or data.get("resourceSpans") or (data.get("trace") or {}).get("resourceSpans") or []:
        res = {x["key"]: attr_value(x["value"]) for x in (rs.get("resource") or {}).get("attributes") or []}
        for ss in rs.get("scopeSpans") or rs.get("instrumentationLibrarySpans") or []:
            for s in ss.get("spans") or []:
                spans.append({**s, "service": res.get("service.name", "?")})
    if not spans:
        die(f"trace {a.trace_id} has no spans")
    start = min(int(s["startTimeUnixNano"]) for s in spans)
    ids = {s.get("spanId") for s in spans}
    children = {}
    for s in sorted(spans, key=lambda s: int(s["startTimeUnixNano"])):
        parent = s.get("parentSpanId") if s.get("parentSpanId") in ids else None
        children.setdefault(parent, []).append(s)

    def show(s, depth):
        t0, t1 = int(s["startTimeUnixNano"]), int(s["endTimeUnixNano"])
        err = " ERROR" if (s.get("status") or {}).get("code") in (2, "STATUS_CODE_ERROR") else ""
        print(f"{(t0 - start) / 1e6:9.1f} ms {(t1 - t0) / 1e6:9.1f} ms  {'  ' * depth}"
              f"{s['service']}: {s.get('name')}{err}")
        if a.attrs:
            for x in s.get("attributes") or []:
                print(f"{'':24}{'  ' * depth}  {x['key']}={str(attr_value(x['value']))[:a.width]}")
        for c in children.get(s.get("spanId"), []):
            show(c, depth + 1)
    for root in children.get(None, []):
        show(root, 0)
    print(f"obsq: {len(spans)} span(s)", file=sys.stderr)


def cmd_get(a, base, auth):
    params = []
    for kv in a.params:
        k, sep, v = kv.partition("=")
        if not sep:
            die(f"parameters are key=value (got {kv!r})")
        params.append((k, v))
    print(json.dumps(get(base, auth, a.uid, a.path, params), indent=1))


def main():
    p = argparse.ArgumentParser(prog="obsq.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--stack", help="stack.py name whose env file gives GRAFANA_PORT")
    p.add_argument("--loki-uid", default="loki")
    p.add_argument("--tempo-uid", default="tempo")
    p.add_argument("--json", action="store_true", help="print the raw JSON answer")
    p.add_argument("--width", type=int, default=400, help="cut each log line / attribute here")
    s = p.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("loki", help="LogQL over a time range")
    q.add_argument("query")
    q.add_argument("--since", default="1h")
    q.add_argument("--limit", type=int, default=50)
    q.add_argument("--labels", default="service_name,level",
                   help="comma list of stream labels to show per line")
    q = s.add_parser("traces", help="TraceQL search")
    q.add_argument("query")
    q.add_argument("--since", default="1h")
    q.add_argument("--limit", type=int, default=20)
    q = s.add_parser("trace", help="one trace as a span tree")
    q.add_argument("trace_id")
    q.add_argument("--attrs", action="store_true", help="show span attributes")
    q = s.add_parser("get", help="any read-only GET through the proxy, e.g. get mimir api/v1/query query=up")
    q.add_argument("uid")
    q.add_argument("path")
    q.add_argument("params", nargs="*")
    a = p.parse_args()
    if a.cmd == "loki":
        a.labels = [x.strip() for x in a.labels.split(",") if x.strip()]
    base, auth = target(a)
    {"loki": cmd_loki, "traces": cmd_traces, "trace": cmd_trace, "get": cmd_get}[a.cmd](a, base, auth)


if __name__ == "__main__":
    main()
