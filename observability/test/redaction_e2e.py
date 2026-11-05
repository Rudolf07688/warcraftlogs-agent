"""End-to-end redaction (feature 060, sc-423, spec §10 and §12 P7): seeded secrets never reach
a backend unmasked, whatever path they enter by.

Every run makes fresh random secrets (``SHAPES``), sends each one through every telemetry path
(``PATHS``), then reads back everything Loki, Tempo and Mimir stored for the run (log lines and
their structured metadata, whole traces with span attributes and events, every series' labels
including ``target_info``) and fails if any raw value appears. Each path must also have arrived
in each backend it feeds, so a path that silently stopped can't pass by sending nothing.

To cover a new shape or path, add one row to SHAPES or PATHS.

    python3 redaction_e2e.py --otlp http://127.0.0.1:24318 --faro http://127.0.0.1:24347/collect \
        --grafana http://127.0.0.1:23000

Standard library only (the backend path runs the app's bootstrap under ``uv``). Exit 0 = clean.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from redaction_check import Checker, rand, str_attr

REPO = Path(__file__).resolve().parents[2]

# name -> (raw secret generator, the text that carries it). The raw value must never be stored.
SHAPES: dict[str, tuple[Callable[[], str], str]] = {
    "bearer": (lambda: f"tok{rand(32)}", "Authorization: Bearer {}"),
    "jwt": (lambda: f"eyJ{rand(20)}.eyJ{rand(30)}.{rand(43)}", "id_token {}"),
    "sk": (lambda: f"sk-ant-api03-{rand(40)}", "anthropic key {}"),
    "aiza": (lambda: f"AIza{rand(35)}", "google key {}"),
    "dsn": (lambda: f"pw{rand(16)}", "db postgresql+asyncpg://app:{}@db:5432/wcl"),
}


def now_ns() -> str:
    return f"{time.time_ns()}"


def send_build(c: Checker, run: dict) -> dict:
    """The build layer: OTLP shaped like Claude Code's (service.name claude-code, its event names,
    tool output as a span event, a metric with attributes)."""
    texts, marker = run["texts"], run["marker"]
    trace_id, span_id = secrets.token_hex(16), secrets.token_hex(8)
    resource = {"attributes": [str_attr("service.name", "claude-code")]
                + [str_attr(f"seed.{s}", t) for s, t in texts.items()]}
    attrs = [str_attr(f"seed.{s}", t) for s, t in texts.items()]
    logs = [
        {"timeUnixNano": now_ns(), "severityText": "INFO", "traceId": trace_id, "spanId": span_id,
         "body": {"stringValue": f"{marker} {event} {' '.join(texts.values())}"},
         "attributes": [str_attr("event.name", event), *attrs]}
        for event in ("tool_result", "api_request", "user_prompt")
    ]
    c.post("logs", {"resourceLogs": [{"resource": resource, "scopeLogs": [{"logRecords": logs}]}]})
    span = {"traceId": trace_id, "spanId": span_id, "name": f"{marker}-tool", "kind": 1,
            "startTimeUnixNano": now_ns(), "endTimeUnixNano": now_ns(), "attributes": attrs,
            "events": [{"timeUnixNano": now_ns(), "name": "tool.output", "attributes": attrs}]}
    c.post("traces", {"resourceSpans": [{"resource": resource, "scopeSpans": [{"spans": [span]}]}]})
    metric = {"name": f"claude_code.redaction_e2e_{run['id']}",
              "sum": {"aggregationTemporality": 2, "isMonotonic": True, "dataPoints": [
                  {"timeUnixNano": now_ns(), "asDouble": 1, "attributes": [str_attr("tool_name", t)]}
                  for t in texts.values()]}}
    c.post("metrics", {"resourceMetrics": [{"resource": resource, "scopeMetrics": [{"metrics": [metric]}]}]})
    return {"service": "claude-code", "trace_id": trace_id, "metric": f'{{__name__=~"claude_code_redaction_e2e_{run["id"]}.*"}}'}


def send_backend(c: Checker, run: dict) -> dict:
    """The runtime layer through the real bootstrap (backend/app/telemetry), in a subprocess."""
    env = {
        "HOME": os.environ.get("HOME", ""),
        "PATH": os.environ.get("PATH", ""),
        "OTEL_EXPORTER_OTLP_ENDPOINT": c.otlp,
        "OTEL_METRIC_EXPORT_INTERVAL": "1000",
        "OTEL_RESOURCE_ATTRIBUTES": ",".join(f"seed.{s}={t.replace(',', ' ')}" for s, t in run["texts"].items()),
        "WCL_ENVIRONMENT": "dev",
        "WCL_GIT_SHA": "e2e" + run["id"][:4].lower(),
        "WCL_LOAD_DOTENV": "0",  # never the owner's .env
    }
    out = subprocess.run(
        ["uv", "run", "--quiet", "python", str(REPO / "observability/test/redaction_e2e_backend.py")],
        input=json.dumps({"marker": run["marker"], "texts": run["texts"]}),
        capture_output=True, text=True, env=env, cwd=REPO, timeout=300, check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"backend bootstrap failed: {out.stderr[-2000:]}")
    return {"service": "api", "trace_id": out.stdout.split()[-1], "metric": '{__name__=~"app_redaction_e2e.*"}'}


def send_faro(c: Checker, run: dict, faro: str) -> dict:
    """The browser: one receiver payload with a log, an exception, an event, a measurement's
    context and a span, as Faro sends them."""
    import urllib.request

    texts, marker = run["texts"], run["marker"]
    joined = " ".join(texts.values())
    ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    trace_id, span_id = secrets.token_hex(16), secrets.token_hex(8)
    payload = {
        "meta": {"sdk": {"name": "@grafana/faro-core", "version": "2.13.0"},
                 "app": {"name": "web", "namespace": "wcl-agent", "version": "e2e", "environment": "dev"},
                 "session": {"id": f"e2e-{run['id']}"}, "page": {"url": "http://localhost:5173/app"},
                 "view": {"name": "/app/*"}},
        "logs": [{"message": f"{marker} log {joined}", "level": "error", "context": dict(texts), "timestamp": ts}],
        "exceptions": [{"type": "Error", "value": f"{marker} exception {joined}", "timestamp": ts,
                        "context": dict(texts)}],
        "events": [{"name": "agent_message_sent", "attributes": {f"m_{s}": t for s, t in texts.items()} | {"marker": marker},
                    "timestamp": ts}],
        "measurements": [{"type": "web-vitals", "values": {"lcp": 1}, "context": {"marker": marker, **texts}, "timestamp": ts}],
        "traces": {"resourceSpans": [{"resource": {"attributes": [str_attr("service.name", "web")]},
                                      "scopeSpans": [{"scope": {"name": "e2e"}, "spans": [{
                                          "traceId": trace_id, "spanId": span_id, "name": f"{marker}-fetch", "kind": 3,
                                          "startTimeUnixNano": now_ns(), "endTimeUnixNano": now_ns(),
                                          "attributes": [str_attr(f"seed.{s}", t) for s, t in texts.items()],
                                          "events": [{"timeUnixNano": now_ns(), "name": "seed",
                                                      "attributes": [str_attr(f"seed.{s}", t) for s, t in texts.items()]}],
                                      }]}]}]},
    }
    req = urllib.request.Request(faro, data=json.dumps(payload).encode(), headers={
        "Content-Type": "application/json", "Origin": "http://localhost:5173", "x-api-key": "wcl-faro-local"})
    urllib.request.urlopen(req, timeout=10).read()
    return {"service": "web", "trace_id": trace_id, "metric": None}


# name -> (sender, the Loki line count it must leave). The Postgres log (058) is not a row:
# observability/test/datastores.sh seeds a secret through it and proves it masked.
PATHS: dict[str, tuple[Callable[..., dict], int]] = {
    "build": (send_build, 3),
    "backend": (send_backend, len(SHAPES)),
    "faro": (send_faro, 4),  # log, exception, event, measurement
}


def run(otlp: str, faro: str, grafana: str) -> int:
    c = Checker(otlp, grafana)
    run_id = rand(8)
    raw: dict[tuple[str, str], str] = {}
    sent: dict[str, dict] = {}
    for path, (sender, _) in PATHS.items():
        values = {shape: gen() for shape, (gen, _) in SHAPES.items()}
        texts = {shape: SHAPES[shape][1].format(v) for shape, v in values.items()}
        raw |= {(path, shape): v for shape, v in values.items()}
        marker = f"e2e-{run_id}-{path}"
        args = (faro,) if path == "faro" else ()
        sent[path] = sender(c, {"id": run_id, "marker": marker, "texts": texts}, *args) | {"marker": marker}

    stored: dict[str, str] = {}  # backend -> everything it returned for this run
    for path, info in sent.items():
        want = PATHS[path][1]
        lines = c.poll(lambda: (r := c.loki(f'{{service_name=~".+"}} |= "{info["marker"]}"'))
                       and sum(len(s["values"]) for s in r) >= want and r, 120)
        c.check(bool(lines), f"{path}: {want} log lines stored in Loki")
        stored["loki"] = stored.get("loki", "") + json.dumps(lines)
        trace = c.poll(lambda: json.dumps(json.loads(c.get("tempo", f"api/v2/traces/{info['trace_id']}"))), 120)
        c.check(bool(trace) and info["marker"] in (trace or ""), f"{path}: trace stored in Tempo")
        c.check('"seed.event"' in (trace or "") or '"tool.output"' in (trace or "") or '"seed"' in (trace or ""),
                f"{path}: span events stored in Tempo")
        stored["tempo"] = stored.get("tempo", "") + (trace or "")
        if info["metric"]:
            series = c.poll(lambda: json.loads(c.get("mimir", "api/v1/series", {"match[]": info["metric"]}))["data"], 120)
            c.check(bool(series), f"{path}: metric series stored in Mimir")
            target = c.poll(lambda: json.loads(c.get("mimir", "api/v1/series", {
                "match[]": f'target_info{{job="wcl-agent/{info["service"]}"}}'}))["data"], 120)
            c.check(bool(target), f"{path}: resource stored as Mimir target_info")
    # Every series Mimir holds, so a secret that became any label anywhere is found.
    stored["mimir"] = c.get("mimir", "api/v1/series", {"match[]": '{__name__=~".+"}'})

    everything = "".join(stored.values())
    for (path, shape), value in sorted(raw.items()):
        where = [b for b, text in stored.items() if value in text]
        c.check(not where, f"{path}: raw {shape} absent from Loki, Tempo and Mimir" + (f" (found in {where})" if where else ""))
    c.check(all("<redacted>" in stored[b] for b in ("loki", "tempo", "mimir")), "Alloy's masks are visible in Loki, Tempo and Mimir")
    c.check(len(everything) > 1000, f"backends returned data ({len(everything)} bytes)")
    print(f"redaction e2e: {c.failures} failure(s)")
    return 1 if c.failures else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--otlp", required=True)
    ap.add_argument("--faro", required=True)
    ap.add_argument("--grafana", required=True)
    a = ap.parse_args()
    sys.exit(run(a.otlp, a.faro, a.grafana))
