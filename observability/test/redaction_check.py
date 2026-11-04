"""Seed secrets through Alloy and check what Loki, Tempo and Mimir stored (feature 053, sc-401).

Runs against a stack that is already up (redaction.sh and mutation.sh bring it up). Every
run uses fresh random secrets, so an older run's data can't make it pass. Exit 0 = every
check passed. Standard library only.

    python3 redaction_check.py --otlp http://127.0.0.1:24318 --grafana http://127.0.0.1:23000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import string
import sys
import time
import urllib.parse
import urllib.request

ALNUM = string.ascii_letters + string.digits
BANNED_METRIC_LABELS = ["session_id", "prompt_id", "user_account_uuid", "user_email", "client_request_id"]
HASHED_KEYS = ["access_token", "refresh_token", "client_secret", "authorization", "api_key", "password"]


def rand(n: int) -> str:
    return "".join(secrets.choice(ALNUM) for _ in range(n))


def seed() -> dict[str, str]:
    """One secret per shape; the raw value must never be stored."""
    return {
        "jwt": f"eyJ{rand(20)}.eyJ{rand(30)}.{rand(43)}",
        "bearer": f"tok{rand(32)}",  # sent as "Bearer <value>"
        "sk": f"sk-ant-api03-{rand(40)}",
        "aiza": f"AIza{rand(35)}",
        "dsn_password": f"pw{rand(16)}",  # inside postgresql+asyncpg://app:<pw>@db:5432/wcl
    }


def str_attr(key: str, value: str) -> dict:
    return {"key": key, "value": {"stringValue": value}}


def secret_text(s: dict[str, str]) -> str:
    return (
        f"jwt={s['jwt']} auth=Bearer {s['bearer']} anthropic={s['sk']} google={s['aiza']} "
        f"dsn=postgresql+asyncpg://app:{s['dsn_password']}@db:5432/wcl"
    )


def secret_attrs(s: dict[str, str], hashed: dict[str, str]) -> list[dict]:
    attrs = [
        str_attr("seed.jwt", s["jwt"]),
        str_attr("seed.bearer", f"Bearer {s['bearer']}"),
        str_attr("seed.sk", s["sk"]),
        str_attr("seed.aiza", s["aiza"]),
        str_attr("seed.dsn", f"postgres://app:{s['dsn_password']}@db/wcl"),
        str_attr("seed.text", secret_text(s)),
    ]
    attrs += [str_attr(k, v) for k, v in hashed.items()]
    return attrs


class Checker:
    def __init__(self, otlp: str, grafana: str) -> None:
        self.otlp = otlp.rstrip("/")
        self.grafana = grafana.rstrip("/")
        self.failures = 0

    def check(self, ok: bool, what: str) -> None:
        print(("PASS  " if ok else "FAIL  ") + what)
        if not ok:
            self.failures += 1

    def post(self, signal: str, payload: dict) -> None:
        req = urllib.request.Request(
            f"{self.otlp}/v1/{signal}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10).read()

    def get(self, uid: str, path: str, params: dict | None = None, accept: str = "application/json") -> str:
        url = f"{self.grafana}/api/datasources/proxy/uid/{uid}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Accept": accept})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode()

    def poll(self, fn, seconds: int = 90):
        """Call fn until it returns something truthy (errors count as 'not yet')."""
        deadline = time.time() + seconds
        while True:
            try:
                got = fn()
                if got:
                    return got
            except Exception:
                pass
            if time.time() >= deadline:
                return None
            time.sleep(3)

    def loki(self, query: str) -> list[dict]:
        start = f"{int(time.time()) - 3600}000000000"
        body = json.loads(self.get("loki", "loki/api/v1/query_range", {"query": query, "start": start, "limit": 100}))
        return body["data"]["result"]


def run(otlp: str, grafana: str) -> int:
    c = Checker(otlp, grafana)
    run_id = rand(8)
    now = f"{int(time.time())}000000000"
    stored_raw: dict[str, str] = {}  # what each layer wrote, every backend answer concatenated

    for layer, service, content_event in (
        ("build", "claude-code", "user_prompt"),
        ("runtime", "wcl-backend", "gen_ai.user.message"),
    ):
        s = seed()
        hashed = {k: f"{k}-{rand(16)}" for k in HASHED_KEYS}
        trace_id, span_id = secrets.token_hex(16), secrets.token_hex(8)
        # The build layer relies on Alloy stamping app.layer from service.name.
        res_attrs = [str_attr("service.name", service), str_attr("seed.resource", s["sk"])]
        if layer == "runtime":
            res_attrs.append(str_attr("app.layer", "runtime"))
        resource = {"attributes": res_attrs}
        marker = f"redaction-{run_id}-{layer}"

        logs = [
            {  # plain log: string body + attributes
                "timeUnixNano": now,
                "severityText": "INFO",
                "body": {"stringValue": f"{marker} plain {secret_text(s)}"},
                "attributes": secret_attrs(s, hashed),
                "traceId": trace_id,
                "spanId": span_id,
            },
            {  # map body (structured GenAI-style event), also a content event
                "timeUnixNano": now,
                "severityText": "INFO",
                "body": {"kvlistValue": {"values": [str_attr("content", f"{marker} content {secret_text(s)}")]}},
                "attributes": [str_attr("event.name", content_event)],
                "traceId": trace_id,
                "spanId": span_id,
            },
        ]
        c.post("logs", {"resourceLogs": [{"resource": resource, "scopeLogs": [{"logRecords": logs}]}]})

        span = {
            "traceId": trace_id,
            "spanId": span_id,
            "name": f"{marker}-span",
            "kind": 1,
            "startTimeUnixNano": now,
            "endTimeUnixNano": now,
            "attributes": secret_attrs(s, hashed),
            # Claude Code's tool.output content arrives as a span event.
            "events": [{"timeUnixNano": now, "name": "tool.output", "attributes": secret_attrs(s, hashed)}],
        }
        c.post("traces", {"resourceSpans": [{"resource": resource, "scopeSpans": [{"spans": [span]}]}]})

        metric_attrs = [
            str_attr("session.id", f"sess-{run_id}"),
            str_attr("prompt.id", f"prompt-{run_id}"),
            str_attr("user.account_uuid", f"acct-{run_id}"),
            str_attr("user.email", f"{run_id}@example.com"),
            str_attr("client_request_id", f"req-{run_id}"),
            str_attr("agent.name", "developer"),
        ]
        metric_res = {"attributes": res_attrs + [str_attr("session.id", f"sess-{run_id}")]}
        metric = {
            "name": f"redaction_test_{run_id}_{layer}",
            "gauge": {"dataPoints": [{"timeUnixNano": now, "asDouble": 1, "attributes": metric_attrs}]},
        }
        c.post("metrics", {"resourceMetrics": [{"resource": metric_res, "scopeMetrics": [{"metrics": [metric]}]}]})

        # --- what the backends stored ---
        sel = f'{{service_name="{service}", app_layer="{layer}"}}'
        log_streams = c.poll(lambda: (r := c.loki(f'{sel} |= "{marker}"')) and len(sum((x["values"] for x in r), [])) >= 2 and r)
        # Re-serialised: Tempo's Go encoder writes "<" as \u003c.
        trace = c.poll(lambda: json.dumps(json.loads(c.get("tempo", f"api/v2/traces/{trace_id}"))))
        series = c.poll(lambda: json.loads(c.get("mimir", "api/v1/series", {"match[]": metric["name"]}))["data"])
        target_info = c.poll(
            lambda: json.loads(c.get("mimir", "api/v1/series", {"match[]": f'target_info{{job="wcl-agent/{service}"}}'}))["data"]
        )

        c.check(bool(log_streams), f"{layer}: both logs stored in Loki with app_layer={layer}")
        c.check(bool(trace), f"{layer}: span stored in Tempo")
        c.check(bool(series), f"{layer}: metric stored in Mimir")
        c.check(bool(target_info), f"{layer}: resource stored as Mimir target_info")
        stored = json.dumps(log_streams) + (trace or "") + json.dumps(series) + json.dumps(target_info)
        stored_raw[layer] = stored

        for shape, value in s.items():
            c.check(value not in stored, f"{layer}: raw {shape} secret absent from Loki, Tempo and Mimir")
        for key, value in hashed.items():
            digest = hashlib.sha256(value.encode()).hexdigest()
            c.check(value not in stored and digest in (json.dumps(log_streams) + (trace or "")),
                    f"{layer}: {key} stored as its SHA-256")
        log_text, trace_text = json.dumps(log_streams), trace or ""
        c.check(log_text.count("<redacted>") >= 4 and "<jwt:redacted>" in log_text, f"{layer}: Loki shows the masks")
        c.check(trace_text.count("<redacted>") >= 4 and "<jwt:redacted>" in trace_text, f"{layer}: Tempo shows the masks")
        c.check('"tool.output"' in trace_text and trace_text.count("<jwt:redacted>") >= 3,
                f"{layer}: span event attributes masked too")

        labels = set().union(*(set(x) for x in (series or []) + (target_info or [])))
        for banned in BANNED_METRIC_LABELS:
            c.check(banned not in labels, f"{layer}: metric series and target_info carry no {banned}")
        c.check("agent_name" in labels, f"{layer}: allowed metric label agent_name kept")

        content = c.poll(lambda: c.loki(f'{{service_name="{service}", content="true"}} |= "{marker} content"'))
        plain_in_content = c.loki(f'{{service_name="{service}", content="true"}} |= "{marker} plain"')
        plain_rest = c.loki(f'{{service_name="{service}", content=""}} |= "{marker} plain"')
        c.check(bool(content), f"{layer}: {content_event} routed to the content stream")
        c.check(not plain_in_content and bool(plain_rest), f"{layer}: plain log stays out of the content stream")

    print(f"redaction: {c.failures} failure(s)")
    return 1 if c.failures else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--otlp", required=True)
    ap.add_argument("--grafana", required=True)
    args = ap.parse_args()
    sys.exit(run(args.otlp, args.grafana))
