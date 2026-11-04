"""sc-409 checks for red.sh: spans in, RED series and aliases out (see red.sh)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BANNED = {"session_id", "url_full", "db_query_text", "trace_id", "span_id", "user_id",
          "gen_ai_conversation_id", "request_id", "url_path", "http_target"}
failures = 0


def check(ok: bool, msg: str) -> None:
    global failures
    print(("PASS  " if ok else "FAIL  ") + msg)
    failures += 0 if ok else 1


def attrs(d: dict) -> list[dict]:
    return [{"key": k, "value": {"intValue": str(v)} if isinstance(v, int) else {"stringValue": v}}
            for k, v in d.items()]


def span(trace: str, sid: str, name: str, kind: int, dur_ms: int, a: dict, parent: str = "",
         error: bool = False) -> dict:
    end = time.time_ns()
    s = {"traceId": trace, "spanId": sid, "name": name, "kind": kind,
         "startTimeUnixNano": str(end - dur_ms * 1_000_000), "endTimeUnixNano": str(end),
         "attributes": attrs(a), "status": {"code": 2 if error else 1}}
    if parent:
        s["parentSpanId"] = parent
    return s


def resource(service: str, spans: list[dict]) -> dict:
    return {"resource": {"attributes": attrs({"service.name": service, "service.namespace": "wcl-agent",
                                              "app.layer": "runtime", "deployment.environment.name": "dev"})},
            "scopeSpans": [{"scope": {"name": "red-test"}, "spans": spans}]}


def post(otlp: str, body: dict) -> None:
    req = urllib.request.Request(otlp + "/v1/traces", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).read()


def get(grafana: str, path: str, **params) -> dict:
    url = f"{grafana}/api/datasources/proxy/uid/mimir/{path}?{urllib.parse.urlencode(params)}"
    try:
        return json.load(urllib.request.urlopen(url, timeout=10))
    except Exception:
        return {}


def query(grafana: str, q: str) -> list[dict]:
    return (get(grafana, "api/v1/query", query=q).get("data") or {}).get("result") or []


def wait(grafana: str, q: str, secs: int = 300) -> list[dict]:
    deadline = time.time() + secs
    while time.time() < deadline:
        r = query(grafana, q)
        if r:
            return r
        time.sleep(5)
    return []


def send_round(otlp: str, run: str) -> str:
    """One round of traffic. Returns a trace id that carries a /api/reports server span."""
    hx = lambda n: os.urandom(n).hex()  # noqa: E731
    secret = {"session.id": f"sess-{run}", "url.full": f"http://api/api/reports?x={run}",
              "user.id": f"user-{run}", "db.query.text": f"select '{run}'", "enduser.id": run}
    web, api = [], []
    keep = ""
    for i in range(6):
        t, client, server = hx(16), hx(8), hx(8)
        keep = keep or t
        web.append(span(t, client, "GET", 3, 40, {"http.request.method": "GET", **secret}))
        api.append(span(t, server, "GET /api/reports", 2, 30 + i, {
            "http.route": "/api/reports", "http.status_code": 200, **secret}, parent=client))
    t = hx(16)
    api.append(span(t, hx(8), "GET /api/reports", 2, 50, {"http.route": "/api/reports", "http.status_code": 500},
                    error=True))
    for route, ms in (("/ws/chat", 20000), ("/api/guides/{guide_id}/generate", 15000)):
        api.append(span(hx(16), hx(8), route, 2, ms, {"http.route": route, **secret}))
    post(otlp, {"resourceSpans": [resource("web", web), resource("api", api)]})
    return keep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--otlp", required=True)
    ap.add_argument("--grafana", required=True)
    a = ap.parse_args()
    run = os.urandom(4).hex()

    traces = {send_round(a.otlp, run)}
    calls = 'traces_spanmetrics_calls{service_name="api", http_route="/api/reports"}'
    check(bool(wait(a.grafana, calls, 180)), "spanmetrics calls series per http.route")
    # Counters need two samples for rate(): keep sending for a while.
    for _ in range(8):
        time.sleep(15)
        traces.add(send_round(a.otlp, run))

    series = get(a.grafana, "api/v1/series", **{"match[]": '{__name__=~"traces_spanmetrics_.*|traces_service_graph_.*"}'})
    labels = {k for s in series.get("data") or [] for k in s}
    values = {v for s in series.get("data") or [] for v in s.values()}
    check(bool(labels) and not (labels & BANNED), f"no id/URL/SQL/session label on RED series (labels: {sorted(labels)})")
    check(not any(run in v for v in values), "no label value carries a per-request value")
    check({"http_route", "status_code", "span_kind", "service_name"} <= labels, "dimensions present")

    ex = get(a.grafana, "api/v1/query_exemplars",
             query='traces_spanmetrics_duration_bucket{service_name="api", http_route="/api/reports"}',
             start=str(time.time() - 900), end=str(time.time() + 60))
    ids = {e["labels"].get("trace_id") or e["labels"].get("traceID")
           for s in ex.get("data") or [] for e in s.get("exemplars", [])}
    check(bool(ids & traces), f"latency exemplars link to sent traces ({len(ids)} exemplars)")

    check(bool(wait(a.grafana, 'traces_service_graph_request_total{client="web", server="api"}', 120)),
          "service graph edge web -> api")

    rate = wait(a.grafana, 'app:http_requests:rate5m{service_name="api", http_route="/api/reports"}', 240)
    codes = {r["metric"].get("status_code") for r in rate}
    check({"STATUS_CODE_OK", "STATUS_CODE_ERROR"} <= codes, f"app:http_requests:rate5m by status_code ({codes})")
    check(set(rate[0]["metric"]) <= {"__name__", "service_name", "http_route", "status_code"} if rate else False,
          "app:http_requests:rate5m keeps only service_name, http_route, status_code")
    p95 = wait(a.grafana, 'app:http_latency:p95{service_name="api"}', 240)
    routes = {r["metric"].get("http_route") for r in p95}
    check("/api/reports" in routes, "app:http_latency:p95 for /api/reports")
    check("/ws/chat" not in routes and not any(r.endswith("/generate") for r in routes if r),
          f"app:http_latency:p95 leaves out /ws/chat and .*/generate ({routes})")
    total = query(a.grafana, 'sum by (http_route) (app:http_requests:rate5m{service_name="api"})')
    check({"/ws/chat", "/api/guides/{guide_id}/generate"} <= {r["metric"].get("http_route") for r in total},
          "the request-rate alias still counts the streaming routes")

    print(f"red: {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
