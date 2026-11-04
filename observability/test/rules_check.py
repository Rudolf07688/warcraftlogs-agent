"""Checks for rules.sh (feature 055): rules load, build aliases, cost arithmetic, price history."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

failures = 0
CLAUDE, GEMINI = "claude-sonnet-5-5", "gemini-3.6-flash"


def check(ok: bool, msg: str) -> None:
    global failures
    print(("PASS  " if ok else "FAIL  ") + msg)
    failures += 0 if ok else 1


def attrs(d: dict) -> list[dict]:
    return [{"key": k, "value": {"stringValue": v}} for k, v in d.items()]


def resource(service: str, metrics: list[dict], layer: str) -> dict:
    return {"resource": {"attributes": attrs({"service.name": service, "service.namespace": "wcl-agent",
                                              "app.layer": layer, "deployment.environment.name": "dev"})},
            "scopeMetrics": [{"scope": {"name": "rules-test"}, "metrics": metrics}]}


def push(otlp: str, body: dict) -> None:
    req = urllib.request.Request(otlp + "/v1/metrics", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).read()


def get(grafana: str, path: str, **params) -> dict:
    url = f"{grafana}/api/datasources/proxy/uid/mimir/{path}?{urllib.parse.urlencode(params)}"
    try:
        return json.load(urllib.request.urlopen(url, timeout=15))
    except Exception:
        return {}


def query(grafana: str, q: str, at: float | None = None) -> list[dict]:
    params = {"query": q} | ({"time": f"{at:.3f}"} if at else {})
    return (get(grafana, "api/v1/query", **params).get("data") or {}).get("result") or []


def wait(grafana: str, q: str, secs: int = 300, pred=bool) -> list[dict]:
    deadline = time.time() + secs
    while time.time() < deadline:
        r = query(grafana, q)
        if r and pred(r):
            return r
        time.sleep(5)
    return []


def counter(name: str, unit: str, points: list[tuple[dict, float]], start: int, now: int) -> dict:
    return {"name": name, "unit": unit, "sum": {"aggregationTemporality": 2, "isMonotonic": True, "dataPoints": [
        {"startTimeUnixNano": str(start), "timeUnixNano": str(now), "asDouble": v, "attributes": attrs(a)}
        for a, v in points]}}


def token_hist(points: list[tuple[dict, float, int]], start: int, now: int) -> dict:
    """gen_ai.client.token.usage as the backend exports it: an exponential histogram."""
    dps = []
    for a, total, count in points:
        dps.append({"startTimeUnixNano": str(start), "timeUnixNano": str(now), "count": str(count), "sum": total,
                    "scale": 0, "zeroCount": "0", "positive": {"offset": 9, "bucketCounts": [str(count)]},
                    "attributes": attrs(a)})
    return {"name": "gen_ai.client.token.usage", "unit": "{token}",
            "exponentialHistogram": {"aggregationTemporality": 2, "dataPoints": dps}}


def send(otlp: str, step: int, start: int) -> None:
    now = time.time_ns()
    cc = [
        counter("claude_code.cost.usage", "USD", [({"model": "claude-opus-5-5", "agent.name": "developer"}, 0.5 * step),
                                                  ({"model": "claude-opus-5-5"}, 0.25 * step)], start, now),
        counter("claude_code.token.usage", "tokens", [
            ({"model": "claude-opus-5-5", "type": "cacheRead", "agent.name": "developer"}, 3000.0 * step),
            ({"model": "claude-opus-5-5", "type": "input", "agent.name": "developer"}, 1000.0 * step),
            ({"model": "claude-opus-5-5", "type": "output", "agent.name": "developer"}, 1000.0 * step),
            ({"model": "claude-opus-5-5", "type": "cacheCreation", "agent.name": "developer"}, 1000.0 * step)], start, now),
        counter("claude_code.session.count", "count", [({}, 1.0 * step)], start, now),
        counter("claude_code.active_time.total", "s", [({"type": "cli"}, 30.0 * step)], start, now),
        counter("claude_code.lines_of_code.count", "count", [({"type": "added"}, 10.0 * step)], start, now),
        counter("claude_code.commit.count", "count", [({}, 1.0 * step)], start, now),
        counter("claude_code.pull_request.count", "count", [({}, 1.0 * step)], start, now),
        counter("claude_code.code_edit_tool.decision", "count", [
            ({"decision": "accept", "language": "Python", "tool_name": "Edit"}, 3.0 * step),
            ({"decision": "reject", "language": "Python", "tool_name": "Edit"}, 1.0 * step)], start, now),
    ]
    # One chat turn per step per model: Claude through the anthropic provider with a dated id,
    # Gemini through Vertex.
    runtime = [token_hist([
        ({"gen_ai.request.model": f"{CLAUDE}-20260101", "gen_ai.token.type": "input", "gen_ai.agent.name": "wcl_agent"}, 12000.0 * step, step),
        ({"gen_ai.request.model": f"{CLAUDE}-20260101", "gen_ai.token.type": "output", "gen_ai.agent.name": "wcl_agent"}, 800.0 * step, step),
        ({"gen_ai.request.model": GEMINI, "gen_ai.token.type": "input", "gen_ai.agent.name": "wcl_agent"}, 20000.0 * step, step),
        ({"gen_ai.request.model": GEMINI, "gen_ai.token.type": "output", "gen_ai.agent.name": "wcl_agent"}, 1500.0 * step, step),
    ], start, now)]
    push(otlp, {"resourceMetrics": [resource("claude-code", cc, "build"), resource("api", runtime, "runtime")]})


def prices_from(path: str) -> dict[tuple[str, str], float]:
    """USD per token from the generated cost.yaml (the rules Mimir runs)."""
    text = open(path).read()
    out = {}
    for m in re.finditer(r"expr: vector\(([^)]+)\)\n\s+labels:\n\s+gen_ai_request_model: (\S+)\n\s+gen_ai_token_type: (\S+)", text):
        out[(m.group(2), m.group(3))] = float(m.group(1))
    return out


def expected_cost(grafana: str, prices: dict, at: float) -> dict[str, float]:
    rates = query(grafana, 'sum by (gen_ai_request_model, gen_ai_token_type) '
                           '(histogram_sum(rate(gen_ai_client_token_usage{service_name="api"}[5m])))', at)
    cost: dict[str, float] = {}
    for r in rates:
        model = re.sub(r"(@\d{8}|-\d{8})$", "", r["metric"]["gen_ai_request_model"])
        cost[model] = cost.get(model, 0.0) + float(r["value"][1]) * prices[(model, r["metric"]["gen_ai_token_type"])]
    return cost


def recorded_cost(grafana: str, at: float | None = None) -> dict[str, float]:
    return {r["metric"]["gen_ai_request_model"]: float(r["value"][1])
            for r in query(grafana, 'sum by (gen_ai_request_model) (genai:cost_usd:rate5m)', at)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--otlp", required=True)
    ap.add_argument("--grafana", required=True)
    ap.add_argument("--pricing", required=True)
    ap.add_argument("--cost-rules", required=True)
    a = ap.parse_args()

    groups = wait(a.grafana, "vector(1)", 30) and get(a.grafana, "api/v1/rules").get("data", {}).get("groups", [])
    files = {g["file"].rsplit("/", 1)[-1] for g in groups or []}
    check({"build.yaml", "red.yaml", "cost.yaml"} <= files, f"rule files loaded: {sorted(files)}")

    start = time.time_ns() - 240 * 10**9
    for step in range(1, 7):
        send(a.otlp, step, start)
        time.sleep(15)

    health = []
    deadline = time.time() + 150
    while time.time() < deadline:
        groups = get(a.grafana, "api/v1/rules").get("data", {}).get("groups", [])
        health = [(r["name"], r.get("health"), r.get("lastError")) for g in groups for r in g["rules"]]
        if health and all(h == "ok" for _, h, _ in health):
            break
        time.sleep(10)
    bad = [h for h in health if h[1] != "ok"]
    check(bool(health) and not bad, f"every rule evaluates without error ({len(health)} rules; bad: {bad[:3]})")

    for alias in ("cc:cost_usd:rate5m", "cc:cost_usd:rate1h", "cc:tokens:rate5m", "cc:sessions:rate5m",
                  "cc:active_time_seconds:rate5m", "cc:lines_of_code:rate5m", "cc:commits:rate5m",
                  "cc:pull_requests:rate5m", "cc:edit_decisions:rate5m"):
        check(bool(wait(a.grafana, alias, 120)), f"{alias} has data")
    by_agent = {r["metric"].get("agent_name", "") for r in query(a.grafana, "cc:cost_usd:rate5m")}
    check({"developer", ""} <= by_agent, f"cc:cost_usd:rate5m keeps agent_name (main session = empty) {by_agent}")
    ratio = wait(a.grafana, "cc:cache_hit_ratio", 120)
    check(bool(ratio) and abs(float(ratio[0]["value"][1]) - 0.5) < 0.01, f"cc:cache_hit_ratio = 3000/6000 ({ratio and ratio[0]['value'][1]})")

    prices = prices_from(a.cost_rules)
    check(len(prices) >= 4, f"{len(prices)} price rows in cost.yaml")
    price_series = wait(a.grafana, "llm_price_usd_per_token", 120)
    check(len(price_series) == len(prices), f"llm_price_usd_per_token has one series per row ({len(price_series)})")

    rec = wait(a.grafana, "genai:cost_usd:rate5m", 180, pred=lambda r: len(r) >= 2)
    check({r["metric"]["gen_ai_request_model"] for r in rec} == {CLAUDE, GEMINI},
          f"genai:cost_usd:rate5m for one Claude and one Gemini model, dated id normalised ({[r['metric'] for r in rec]})")
    check(all(set(r["metric"]) == {"__name__", "gen_ai_request_model", "gen_ai_agent_name"} for r in rec),
          "genai:cost_usd:rate5m is by gen_ai_request_model and gen_ai_agent_name only")
    stamp = query(a.grafana, "max(timestamp(genai:cost_usd:rate5m))")
    t_old = float(stamp[0]["value"][1]) if stamp else time.time()
    got, want = recorded_cost(a.grafana, t_old), expected_cost(a.grafana, prices, t_old)
    for model in (CLAUDE, GEMINI):
        g, w = got.get(model, 0.0), want.get(model, -1.0)
        check(w > 0 and abs(g - w) <= 0.01 * w,
              f"{model}: cost/hour {3600 * g:.4f} USD = tokens x list price {3600 * w:.4f} USD")

    # Price change: double the Claude rows in the mounted copy. Mimir re-reads it within a
    # minute; the cost recorded before keeps the old price.
    text = open(a.cost_rules).read()
    for (model, tt), usd in prices.items():
        if model == CLAUDE:
            text = text.replace(f"expr: vector({usd:.6e})\n    labels:\n      gen_ai_request_model: {model}\n      gen_ai_token_type: {tt}",
                                f"expr: vector({2 * usd:.6e})\n    labels:\n      gen_ai_request_model: {model}\n      gen_ai_token_type: {tt}")
    open(a.cost_rules, "w").write(text)
    new_price = prices[(CLAUDE, "input")] * 2
    changed = wait(a.grafana, f'llm_price_usd_per_token{{gen_ai_request_model="{CLAUDE}", gen_ai_token_type="input"}}',
                   240, pred=lambda r: abs(float(r[0]["value"][1]) - new_price) < 1e-12)
    check(bool(changed), "a price change in the rules loads without a restart")
    old_again = recorded_cost(a.grafana, t_old).get(CLAUDE, 0.0)
    check(abs(old_again - got.get(CLAUDE, -1)) < 1e-12 and old_again > 0,
          "cost recorded before the price change keeps the old price")
    old_price = query(a.grafana, f'llm_price_usd_per_token{{gen_ai_request_model="{CLAUDE}", gen_ai_token_type="input"}}', t_old)
    check(bool(old_price) and abs(float(old_price[0]["value"][1]) - prices[(CLAUDE, "input")]) < 1e-12,
          "the price series still shows the old price at the old time")

    print(f"rules: {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
