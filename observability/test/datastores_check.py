"""Feature 058 checks for datastores.sh: seed real-shaped data, then assert values (see datastores.sh).

Seeds: 200 knowledge-base chunks with 768-d embeddings (the HNSW index of migration 0019), three
traced slow statements issued through the backend's own instrumentation (so the SQL carries the
sqlcommenter traceparent and the trace lands in Tempo) with a secret string, an account-id-like
number and a bound secret in them, a lock wait, an autovacuum run, a long transaction, a
unique-key error quoting a secret e-mail, and 7 Redis hits plus 3 misses.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

failures = 0
SLOW_S = 0.8  # each of the three slow statements; 2.4 s in total keeps it the top statement
DASHBOARDS = {"wcl-d9-postgres", "wcl-d10-redis", "wcl-d11-infra"}
NEW_JOBS = "postgres|redis|cadvisor|alloy|loki|tempo|mimir"


def check(ok: bool, msg: str) -> bool:
    global failures
    print(("PASS  " if ok else "FAIL  ") + msg)
    failures += 0 if ok else 1
    return ok


class Stack:
    def __init__(self, a: argparse.Namespace) -> None:
        self.a = a
        self.owner = os.environ["POSTGRES_USER"]
        self.db = os.environ["POSTGRES_DB"]

    # --- backends through Grafana's datasource proxy -------------------------------------------
    def get(self, path: str, admin: bool = False, **params) -> dict:
        url = f"{self.a.grafana}/{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        req = urllib.request.Request(url)
        if admin:
            import base64
            token = base64.b64encode(f"admin:{os.environ['GRAFANA_ADMIN_PASSWORD']}".encode()).decode()
            req.add_header("Authorization", f"Basic {token}")
        try:
            return json.load(urllib.request.urlopen(req, timeout=20))
        except (urllib.error.URLError, ValueError, TimeoutError):
            return {}

    def mimir(self, q: str) -> list[dict]:
        return (self.get("api/datasources/proxy/uid/mimir/api/v1/query", query=q).get("data") or {}).get("result") or []

    def value(self, q: str) -> float | None:
        r = self.mimir(q)
        return float(r[0]["value"][1]) if r else None

    def loki(self, q: str, limit: int = 200) -> list[tuple[dict, str]]:
        d = self.get("api/datasources/proxy/uid/loki/loki/api/v1/query_range", query=q, limit=str(limit),
                     start=f"{int(time.time()) - 3600}000000000")
        return [(r["stream"], v[1]) for r in (d.get("data") or {}).get("result") or [] for v in r["values"]]

    # --- the compose project --------------------------------------------------------------------
    def dc(self, *args: str, stdin: str | None = None, check_rc: bool = True) -> str:
        r = subprocess.run(["docker", "compose", "-p", self.a.project, *args], cwd=self.a.repo,
                           input=stdin, capture_output=True, text=True, timeout=300)
        if check_rc and r.returncode:
            raise RuntimeError(f"{args}: {r.stderr[-500:]}")
        return r.stdout

    def psql(self, sql: str) -> str:
        return self.dc("exec", "-T", "db", "psql", "-v", "ON_ERROR_STOP=1", "-X", "-qAt", "-U", self.owner,
                       "-d", self.db, "-c", sql).strip()

    def psql_bg(self, script: str) -> subprocess.Popen:
        """A psql session fed line by line (BEGIN, then a pause, then COMMIT): holds a lock or a
        transaction open without a long-running statement of its own."""
        cmd = (f"docker compose -p {self.a.project} exec -T db psql -X -q -U {self.owner} -d {self.db}")
        return subprocess.Popen(["bash", "-c", f"({script}) | {cmd}"], cwd=self.a.repo,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def redis(self, *args: str) -> str:
        return self.dc("exec", "-T", "redis", "redis-cli", *args).strip()


def poll(seconds: float, fn, *args):
    deadline = time.time() + seconds
    while True:
        result = fn(*args)
        if result or time.time() >= deadline:
            return result
        time.sleep(5)


# The backend's instrumentation (backend/app/telemetry/setup.py instrument()) on the app's runtime
# role: one request span, three slow statements. Prints the trace id and the exported SQL span ids.
TRACED = r"""
import asyncio, json, os, sys
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

memory = InMemorySpanExporter()
provider = TracerProvider(resource=Resource.create({"service.name": "api", "service.namespace": "wcl-agent",
                                                    "app.layer": "runtime", "deployment.environment.name": "dev"}))
provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=os.environ["OTLP"] + "/v1/traces")))
provider.add_span_processor(SimpleSpanProcessor(memory))
trace.set_tracer_provider(provider)
from backend.app.telemetry.setup import instrument
instrument()
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    with trace.get_tracer("datastores-test").start_as_current_span("GET /seed") as root:
        async with engine.connect() as conn:
            for _ in range(3):
                await conn.execute(text(
                    "SELECT pg_sleep(%s), 'hunter2-%s' AS pw, %s AS account_id, CAST(:token AS text) AS token"
                    % (os.environ["SLOW_S"], os.environ["SECRET"], os.environ["ACCOUNT"])), {"token": os.environ["BOUND"]})
    await engine.dispose()
    sql = [format(s.context.span_id, "016x") for s in memory.get_finished_spans() if s.name == "SELECT"]
    print(json.dumps({"trace_id": format(root.get_span_context().trace_id, "032x"), "sql_spans": sql}))
    provider.shutdown()

asyncio.run(main())
"""


def seed(s: Stack) -> dict:
    sec = {"secret": secrets.token_hex(8), "account": str(4_200_000_000 + secrets.randbelow(99_999_999)),
           "bound": "sk-bound" + secrets.token_hex(8), "email": f"leak{secrets.token_hex(6)}@example.com",
           "key": "seedkey-" + secrets.token_hex(6)}
    # Knowledge base: one guide, 200 embedded chunks (the HNSW index from 0019 fills).
    s.psql("INSERT INTO spec_guides (id, class_name, spec) VALUES (gen_random_uuid(), 'Mage', 'Fire') ON CONFLICT DO NOTHING")
    s.psql("""INSERT INTO kb_chunks (id, kind, guide_id, chunk_key, label, text, content_hash, embedding)
              SELECT gen_random_uuid(), 'guide', (SELECT id FROM spec_guides LIMIT 1), 'k' || g, 'L', 'chunk ' || g,
                     md5(g::text), e.v
              FROM generate_series(1, 200) g,
                   LATERAL (SELECT array_agg(random())::vector(768) AS v FROM generate_series(1, 768) WHERE g > 0) e""")
    # Traced slow statements through the app's instrumentation.
    env = {"HOME": os.environ["HOME"], "PATH": os.environ["PATH"], "WCL_LOAD_DOTENV": "0", "OTLP": s.a.otlp,
           "SLOW_S": str(SLOW_S), "SECRET": sec["secret"], "ACCOUNT": sec["account"], "BOUND": sec["bound"],
           "DATABASE_URL": f"postgresql+asyncpg://{os.environ['APP_DB_USER']}:{os.environ['APP_DB_PASSWORD']}"
                           f"@127.0.0.1:{os.environ['DB_PORT']}/{s.db}"}
    r = subprocess.run(["uv", "run", "python", "-c", TRACED], cwd=s.a.repo, env=env, capture_output=True,
                       text=True, timeout=300)
    sec |= json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {"trace_id": "", "sql_spans": []}
    check(r.returncode == 0 and len(sec["sql_spans"]) == 3, "three traced slow statements ran through the app's instrumentation"
          + ("" if r.returncode == 0 else f" ({r.stderr[-300:]})"))
    # A lock wait (held 1.6 s, deadlock_timeout 1 s), a long transaction (90 s, no statement of its
    # own), autovacuum on a table that asks for it at once, a unique-key error quoting an e-mail.
    s.psql("CREATE TABLE seed_lock (id int); CREATE TABLE seed_users (email text UNIQUE); "
           "CREATE TABLE seed_vacuum (id int) WITH (autovacuum_vacuum_threshold = 0, autovacuum_vacuum_scale_factor = 0, "
           "autovacuum_analyze_threshold = 0, autovacuum_analyze_scale_factor = 0); "
           "INSERT INTO seed_vacuum SELECT generate_series(1, 2000); DELETE FROM seed_vacuum WHERE id > 100")
    holder = s.psql_bg("echo 'BEGIN; LOCK TABLE seed_lock IN ACCESS EXCLUSIVE MODE;'; sleep 1.6; echo 'COMMIT;'")
    time.sleep(0.3)
    s.psql("SELECT count(*) FROM seed_lock")
    holder.wait(timeout=30)
    sec["long_tx"] = s.psql_bg("echo 'BEGIN; SELECT txid_current();'; sleep 90; echo 'COMMIT;'")
    s.psql(f"INSERT INTO seed_users VALUES ('{sec['email']}')")
    s.dc("exec", "-T", "db", "psql", "-X", "-qAt", "-U", s.owner, "-d", s.db, "-c",
         f"INSERT INTO seed_users VALUES ('{sec['email']}')", check_rc=False)
    # Redis: 7 hits, 3 misses on a fresh instance (nothing else reads keys).
    s.redis("SET", sec["key"], "v")
    for _ in range(7):
        s.redis("GET", sec["key"])
    for i in range(3):
        s.redis("GET", f"{sec['key']}-missing-{i}")
    return sec


def postgres_checks(s: Stack, sec: dict) -> None:
    check(poll(120, s.value, 'pg_up{job="postgres"}') == 1.0, "the exporter reaches Postgres (pg_up 1)")
    role = os.environ["PG_MONITOR_USER"]
    facts = s.psql(f"""SELECT r.rolsuper, r.rolcreaterole, r.rolbypassrls, pg_has_role('{role}', 'pg_monitor', 'member'),
                              (SELECT count(*) FROM pg_class WHERE relowner = r.oid),
                              (SELECT count(*) FROM information_schema.role_table_grants WHERE grantee = '{role}'),
                              (SELECT count(*) FROM pg_stat_activity WHERE usename = '{role}') > 0
                       FROM pg_roles r WHERE r.rolname = '{role}'""")
    check(facts == "f|f|f|t|0|0|t", f"exporter logs in as {role}: pg_monitor member, no superuser, owns nothing, "
          f"no table grants (got {facts})")
    alloy = s.dc("ps", "-q", "alloy").strip()
    ips = subprocess.run(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", alloy],
                         capture_output=True, text=True).stdout.split()
    users = s.psql("SELECT string_agg(DISTINCT usename, ',') FROM pg_stat_activity WHERE host(client_addr) IN ("
                   + ",".join(f"'{ip}'" for ip in ips) + ")")
    check(users == role, f"every session from Alloy's address logs in as {role} (got {users!r})")

    top_sql = s.psql("""SELECT queryid FROM pg_stat_statements WHERE query LIKE '%pg_sleep%' AND query NOT LIKE '%pg_stat_statements%'
                        ORDER BY total_exec_time DESC LIMIT 1""")

    def top_metric():
        r = s.mimir('topk(1, sum by (queryid) (pg_stat_statements_seconds_total{job="postgres"}))')
        return r[0]["metric"].get("queryid") if r and float(r[0]["value"][1]) >= 3 * SLOW_S * 0.9 else None

    got = poll(150, top_metric)
    check(bool(top_sql) and got == top_sql, f"top statement by total time is the seeded slow one (queryid {got} == {top_sql})")

    def top_alias():
        r = s.mimir("topk(1, pg:statement_seconds:total)")
        return r[0]["metric"].get("queryid") if r else None

    # Wait for the ruler's evaluation that includes it: until then the alias's top is an older one.
    got = poll(150, lambda: top_alias() == top_sql) and top_sql or top_alias()
    check(got == top_sql, f"pg:statement_seconds:total (D9's table) ranks it first too (got {got})")

    size = int(s.psql("SELECT pg_relation_size('ix_kb_chunks_embedding')"))
    want = f'pg_vector_index_size_bytes{{job="postgres", index="ix_kb_chunks_embedding"}} == {size}'
    check(size > 8192 and poll(120, s.value, want) == size,
          f"vector index size {size} bytes (> one page) equals pg_relation_size")
    check(poll(150, s.value, f'pg:vector_index:bytes{{index="ix_kb_chunks_embedding"}} == {size}') == size,
          "pg:vector_index:bytes carries the same size")
    check(poll(150, s.value, 'pg_vector_table_rows{job="postgres", table="kb_chunks"} == 200') == 200,
          "embedding table rows: kb_chunks = 200")
    check(poll(180, s.value, "max_over_time(pg:longest_transaction:seconds[5m]) > 20") is not None,
          "the open transaction shows as the longest transaction (> 20 s)")


def redis_checks(s: Stack, sec: dict) -> None:
    check(poll(120, s.value, 'redis_keyspace_hits_total{job="redis"} == 7') == 7, "Redis keyspace hits = 7")
    check(poll(60, s.value, 'redis_keyspace_misses_total{job="redis"} == 3') == 3, "Redis keyspace misses = 3")
    poll(150, lambda: abs((s.value("redis:hit_ratio:5m") or 0) - 0.7) < 0.01)
    ratio = s.value("redis:hit_ratio:5m")
    check(ratio is not None and abs(ratio - 0.7) < 0.01, f"redis:hit_ratio:5m = {ratio} (7 / 10)")


def label_checks(s: Stack, sec: dict) -> None:
    bad = [os.environ["PG_MONITOR_PASSWORD"], os.environ["POSTGRES_PASSWORD"], "postgresql://", "redis://",
           sec["key"], "hunter2", sec["secret"], sec["account"]]
    names = s.get("api/datasources/proxy/uid/mimir/api/v1/labels").get("data") or []
    leaks = []
    for name in names:
        values = s.get(f"api/datasources/proxy/uid/mimir/api/v1/label/{name}/values").get("data") or []
        leaks += [f"{name}={v[:40]}" for v in values if any(b in v for b in bad)]
    check(bool(names) and not leaks, f"no DSN, password, key name or SQL literal in any of {len(names)} label names' values"
          + (f" ({leaks[:3]})" if leaks else ""))
    banned = {"id", "image", "name", "query", "container_label_com_docker_compose_project"}
    series = s.mimir('count by (job) (last_over_time({job="cadvisor"}[2m]))')
    labels = {k for r in s.mimir('last_over_time({job=~"cadvisor|redis|postgres"}[2m])') for k in r["metric"]}
    check(bool(series) and not (labels & banned), f"cAdvisor/exporter series carry no {sorted(banned)} label")
    services = {r["metric"].get("compose_service") for r in s.mimir("infra:container_memory:bytes")}
    own = set(s.dc("ps", "--services").split()) | {"host"}
    check({"db", "redis", "alloy"} <= services <= own, f"container metrics for this project only: {sorted(services)}")
    logs = s.dc("logs", "alloy", check_rc=False)
    ui = json.dumps(s.get_alloy("api/v0/web/components"))
    check(os.environ["PG_MONITOR_PASSWORD"] not in logs + ui, "the monitoring password is not in Alloy's logs or UI")


def loki_checks(s: Stack, sec: dict) -> None:
    def slow():
        return [(m, b) for m, b in s.loki('{service_name="postgres"} |= "pg_sleep"') if m.get("pg_duration_ms")]

    rows = poll(120, lambda: len(slow()) >= 3 and slow())
    check(bool(rows), f"{len(rows or [])} slow-statement records in Loki (> 250 ms)")
    rows = rows or []
    check(all(m.get("trace_id") == sec["trace_id"] for m, _ in rows) and bool(sec["trace_id"]),
          f"each carries the traced request's trace id {sec['trace_id']}")
    check(all(m.get("span_id") in sec["sql_spans"] for m, _ in rows),
          "and the span id of its exported SQL span (the last traceparent)")
    check(all(float(m["pg_duration_ms"]) >= SLOW_S * 1000 for m, _ in rows), "pg_duration_ms >= the sleep")
    everything = "\n".join(b + json.dumps(m) for m, b in s.loki('{service_name="postgres"}', limit=2000))
    for what in ("secret", "account", "bound", "email"):
        check(sec[what] not in everything, f"seeded {what} literal absent from every Postgres record")
    check("parameters:" not in everything, "no bind-parameter details logged")
    check(any("pg_sleep(?)" in b and "'?'" in b for _, b in rows), "the statement text is kept with literals masked")
    check(any(m.get("pg_sqlstate") == "23505" for m, _ in s.loki('{service_name="postgres"} | pg_severity="ERROR"')),
          "the unique-key error is logged (SQLSTATE 23505), its key detail masked")
    ds = s.get("api/datasources/uid/loki", admin=True).get("jsonData", {}).get("derivedFields", [])
    link = [f for f in ds if f.get("matcherType") == "label" and f.get("matcherRegex") == "trace_id"
            and f.get("datasourceUid") == "tempo"]
    check(bool(link), "Loki derived field: trace_id (structured metadata) -> Tempo")
    trace = poll(90, lambda: s.get(f"api/datasources/proxy/uid/tempo/api/v2/traces/{sec['trace_id']}"))
    spans = [sp.get("spanId") for b in (trace or {}).get("trace", {}).get("resourceSpans", [])
             for ss in b.get("scopeSpans", []) for sp in ss.get("spans", [])]
    import base64
    ids = {base64.b64decode(x).hex() if len(x) != 16 else x for x in spans if x}
    check(bool(ids) and set(sec["sql_spans"]) <= ids, "the derived field resolves: Tempo has the trace with those SQL spans")
    waits = poll(60, s.loki, '{service_name="postgres"} |= "still waiting for"')
    check(bool(waits), "lock wait logged (still waiting for ...)")
    vac = poll(150, s.loki, '{service_name="postgres"} |= "automatic vacuum of table \\"wcl.public.seed_vacuum\\""')
    check(bool(vac) and any(ch.isdigit() for _, b in vac for ch in b), "autovacuum run logged with its counters")


def dashboard_checks(s: Stack) -> None:
    for uid in sorted(DASHBOARDS):
        d = s.get(f"api/dashboards/uid/{uid}", admin=True).get("dashboard")
        if not check(bool(d), f"dashboard {uid} provisioned"):
            continue
        for p in [q for p in d["panels"] for q in [p, *p.get("panels", [])]]:
            for t in p.get("targets", []):
                ds = (t.get("datasource") or p.get("datasource") or {}).get("uid")
                if ds == "mimir":
                    q = (t["expr"].replace("$__range", "1h").replace("$__rate_interval", "4m")
                         .replace("$__interval", "1m"))
                    ok = "data" in s.get("api/datasources/proxy/uid/mimir/api/v1/query", query=q)
                elif ds == "loki":
                    ok = "data" in s.get("api/datasources/proxy/uid/loki/loki/api/v1/query_range",
                                         query=t["expr"], limit="1")
                else:
                    continue
                check(ok, f"{uid} '{p['title']}' query is valid")
    added = s.value(f'count(last_over_time({{job=~"{NEW_JOBS}"}}[2m]))')
    active = poll(120, s.value, "meta:active_series:count")
    check(added is not None and added < 5000, f"058 adds {added} series (< 10% of the 50k budget)")
    check(active is not None and 0 < active < 50000, f"meta:active_series:count = {active} (< 50000)")


def main() -> int:
    ap = argparse.ArgumentParser()
    for arg in ("--otlp", "--grafana", "--project", "--repo", "--alloy-ui"):
        ap.add_argument(arg, required=True)
    a = ap.parse_args()
    s = Stack(a)
    s.get_alloy = lambda path: _alloy(a.alloy_ui, path)
    sec = seed(s)
    try:
        postgres_checks(s, sec)
        redis_checks(s, sec)
        loki_checks(s, sec)
        label_checks(s, sec)
        dashboard_checks(s)
    finally:
        sec["long_tx"].kill()
    return 1 if failures else 0


def _alloy(base: str, path: str):
    try:
        return json.load(urllib.request.urlopen(f"{base}/{path}", timeout=20))
    except (urllib.error.URLError, ValueError, TimeoutError):
        return {}


if __name__ == "__main__":
    sys.exit(main())
