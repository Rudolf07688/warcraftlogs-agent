"""sc-424 checks for alerts.sh: each provisioned alert rule goes Firing on its trigger, then Normal."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

failures = 0
RULES = {"wcl-alert-pipeline": "Telemetry pipeline failures or drops",
         "wcl-alert-build-spend": "Build spend per day above threshold"}


def check(ok: bool, msg: str) -> bool:
    global failures
    print(("PASS  " if ok else "FAIL  ") + msg)
    failures += 0 if ok else 1
    return ok


def grafana(base: str, path: str) -> dict:
    token = base64.b64encode(f"admin:{os.environ['GRAFANA_ADMIN_PASSWORD']}".encode()).decode()
    req = urllib.request.Request(f"{base}/{path}", headers={"Authorization": f"Basic {token}"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=15))
    except (urllib.error.URLError, ValueError, TimeoutError):
        return {}


def state(base: str, title: str) -> str:
    """The rule's state as Grafana's ruler reports it: inactive (Normal), pending, firing."""
    for group in (grafana(base, "api/prometheus/grafana/api/v1/rules").get("data") or {}).get("groups", []):
        for rule in group.get("rules", []):
            if rule.get("name") == title:
                return rule.get("state", "")
    return ""


def wait_state(base: str, title: str, want: str, secs: int) -> bool:
    deadline = time.time() + secs
    while time.time() < deadline:
        if state(base, title) == want:
            return True
        time.sleep(5)
    return False


def post(otlp: str, signal: str, body: dict) -> int:
    req = urllib.request.Request(f"{otlp}/v1/{signal}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=10).status
    except urllib.error.HTTPError as e:
        return e.code


def attrs(d: dict) -> list[dict]:
    return [{"key": k, "value": {"stringValue": v}} for k, v in d.items()]


def resource(service: str, layer: str) -> dict:
    return {"attributes": attrs({"service.name": service, "service.namespace": "wcl-agent", "app.layer": layer,
                                 "deployment.environment.name": "dev"})}


def cost(otlp: str, usd: float, start: int) -> None:
    point = {"startTimeUnixNano": str(start), "timeUnixNano": str(time.time_ns()), "asDouble": usd,
             "attributes": attrs({"model": "claude-opus-5-5"})}
    metric = {"name": "claude_code.cost.usage", "unit": "USD",
              "sum": {"aggregationTemporality": 2, "isMonotonic": True, "dataPoints": [point]}}
    post(otlp, "metrics", {"resourceMetrics": [{"resource": resource("claude-code", "build"),
                                                "scopeMetrics": [{"scope": {"name": "alerts-test"}, "metrics": [metric]}]}]})


def log(otlp: str, at_ns: int, text: str) -> int:
    record = {"timeUnixNano": str(at_ns), "observedTimeUnixNano": str(at_ns), "severityText": "INFO",
              "body": {"stringValue": text}}
    return post(otlp, "logs", {"resourceLogs": [{"resource": resource("alerts-test", "runtime"),
                                                 "scopeLogs": [{"scope": {"name": "alerts-test"}, "logRecords": [record]}]}]})


def set_threshold(path: str, usd: float) -> None:
    text = open(path).read()
    new = re.sub(r"(record: alert:build_spend_usd_per_day:threshold\n\s+expr: vector\()[^)]*\)", rf"\g<1>{usd})", text)
    assert new != text or f"vector({usd})" in text, "threshold rule not found"
    open(path, "w").write(new)


def main() -> int:
    ap = argparse.ArgumentParser()
    for arg in ("--otlp", "--grafana", "--rules"):
        ap.add_argument(arg, required=True)
    a = ap.parse_args()

    provisioned = {uid: bool(grafana(a.grafana, f"api/v1/provisioning/alert-rules/{uid}")) for uid in RULES}
    check(all(provisioned.values()), f"alert rules provisioned: {provisioned}")
    for title in RULES.values():
        check(wait_state(a.grafana, title, "inactive", 180), f"'{title}' starts Normal")

    # Build spend: 3 USD of synthetic Claude Code cost against a threshold of 1 USD, then 1e6.
    set_threshold(a.rules, 1)
    start = time.time_ns()
    for i in range(1, 7):
        cost(a.otlp, 0.5 * i, start)
        time.sleep(10)
    spend = RULES["wcl-alert-build-spend"]
    check(wait_state(a.grafana, spend, "firing", 240), f"'{spend}' fires on 3 USD against a 1 USD threshold")
    set_threshold(a.rules, 1000000)
    check(wait_state(a.grafana, spend, "inactive", 240), f"'{spend}' is Normal again after the threshold goes up")

    # Pipeline: a fresh record, then one two hours older on the same stream. Loki answers 400 for
    # good, Alloy's Loki exporter gives the batch up (send_failed_log_records).
    now = time.time_ns()
    check(log(a.otlp, now, "alerts-test fresh") == 200, "fresh log record accepted by Alloy")
    time.sleep(10)
    log(a.otlp, now - 2 * 3600 * 10**9, "alerts-test two hours behind")
    pipeline = RULES["wcl-alert-pipeline"]
    check(wait_state(a.grafana, pipeline, "firing", 240), f"'{pipeline}' fires when Loki refuses a batch for good")
    check(wait_state(a.grafana, pipeline, "inactive", 360), f"'{pipeline}' is Normal again once the 2-minute window passes")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
