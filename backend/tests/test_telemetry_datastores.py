"""Feature 058: data-store telemetry (sc-417, sc-419, sc-420, sc-424) — the parts pytest can prove.

The stack scripts prove the rest on seeded data (observability/test/datastores.sh, alerts.sh):
exporter values, the masked slow-query log in Loki, the trace link, the alert states.

- sqlcommenter: with telemetry on, the SQL the driver gets ends with the traceparent of the
  statement's exported span; with telemetry off it is byte-identical to the statement.
- Migration 0022: the monitoring role only with a password, never a default one, and a role name
  that can't carry SQL.
- D9-D11 and the alert rules read recording-rule aliases only, with sound query shapes.
- The Postgres log masks of config.alloy, run on sample records (row and key details, other
  details, SQL, operational messages).
- The security pins of the compose file and the Alloy section: no Docker access in Alloy (it
  tails Postgres's log files), a hardened cAdvisor, no Redis key checks, no statement text as a
  label, Postgres logs through the redaction chain.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from backend.tests.test_telemetry_metrics_dashboards import metric_names

ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = ROOT / "observability/mimir/rules/anonymous"
DASHBOARDS = ROOT / "observability/grafana/dashboards/infra"
ALERTS = ROOT / "observability/grafana/provisioning/alerting/rules.yaml"
ALLOY = ROOT / "observability/alloy/config.alloy"
COMPOSE = ROOT / "docker-compose.yml"
MIGRATION = ROOT / "backend/migrations/versions/0022_pg_stat_statements.py"
UIDS = {"postgres.json": "wcl-d9-postgres", "redis.json": "wcl-d10-redis", "infra.json": "wcl-d11-infra"}

# --- sqlcommenter -----------------------------------------------------------------------------

# Runs in a fresh interpreter: instrument() patches FastAPI, SQLAlchemy, Redis and HTTPX globally.
_STATEMENT = r"""
import asyncio, json, sys
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

memory = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(memory))
trace.set_tracer_provider(provider)
if sys.argv[1] == "on":
    from backend.app.telemetry.setup import instrument
    instrument()
else:
    from backend.app.telemetry import configure_telemetry
    configure_telemetry()  # no OTLP endpoint: a no-op
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sent = []
    event.listen(engine.sync_engine, "after_cursor_execute", lambda c, cur, statement, *a: sent.append(statement))
    token = None
    if len(sys.argv) > 2:  # a request whose client sent tracestate and baggage
        from opentelemetry import baggage, context
        from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, TraceState
        parent = SpanContext(trace_id=0x1234, span_id=0x5678, is_remote=True, trace_flags=TraceFlags(1),
                             trace_state=TraceState([("vendor", "client-tracestate")]))
        ctx = baggage.set_baggage("client", "client-baggage", trace.set_span_in_context(NonRecordingSpan(parent)))
        token = context.attach(ctx)
    with trace.get_tracer("t").start_as_current_span("request"):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT :a AS answer"), {"a": 42})
    await engine.dispose()
    spans = [format(s.context.span_id, "016x") for s in memory.get_finished_spans() if s.name.startswith("SELECT")]
    print(json.dumps({"sent": sent, "sql_spans": spans}))

asyncio.run(main())
"""


def sent_sql(mode: str, *client: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("OTEL_")}
    r = subprocess.run([sys.executable, "-c", _STATEMENT, mode, *client], cwd=ROOT, env=env, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_telemetry_on_appends_the_traceparent_of_the_exported_sql_span() -> None:
    got = sent_sql("on")
    statement = got["sent"][-1]
    assert statement.startswith("SELECT ? AS answer /*")
    parents = re.findall(r"traceparent='00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}'", statement)
    assert parents, statement
    # Only the traceparent: no driver or framework versions in every statement.
    assert "db_driver" not in statement and "db_framework" not in statement
    # The last one is the exported span (two EngineTracers per async engine, board #31): the
    # slow-query log parser in config.alloy takes the last for this reason.
    assert parents[-1][1] in got["sql_spans"]


def test_client_tracestate_and_baggage_stay_out_of_the_sql() -> None:
    """The propagator would inject them too; the commenter options keep only the traceparent."""
    statement = sent_sql("on", "client")["sent"][-1]
    comments = re.findall(r"/\*(.*?)\*/", statement)
    assert comments and all(re.fullmatch(r"traceparent='00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}'", c) for c in comments), statement
    assert "client-" not in statement and "tracestate" not in statement and "baggage" not in statement


def test_telemetry_off_sends_the_statement_unchanged() -> None:
    assert sent_sql("off")["sent"] == ["SELECT ? AS answer"]


# --- migration 0022 -----------------------------------------------------------------------------


class _Bind:
    """Records what the migration sends (Postgres dialect). ``existing`` answers the monitor-only
    check: None = no such role, "" = monitor-only, text = what is wrong with it."""

    def __init__(self, existing: str | None) -> None:
        self.sql: list[str] = []
        self.existing = existing
        self.dialect = type("D", (), {"name": "postgresql"})()

    def execute(self, statement, params=None):
        text = str(statement)
        self.sql.append(text)
        result = self.existing if "pg_roles r WHERE" in text else "wcl"
        return type("R", (), {"scalar": lambda self: result})()

    def exec_driver_sql(self, statement):
        self.sql.append(statement)


def migration_0022():
    spec = importlib.util.spec_from_file_location("migration_0022", MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def run(monkeypatch, step: str = "upgrade", existing: str | None = None, **env) -> list[str]:
    for key in ("PG_MONITOR_USER", "PG_MONITOR_PASSWORD", "POSTGRES_USER", "APP_DB_USER"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    migration = migration_0022()
    bind = _Bind(existing)
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind, raising=False)
    monkeypatch.setattr(migration.op, "execute", lambda sql: bind.sql.append(str(sql)), raising=False)
    getattr(migration, step)()
    return [q for q in bind.sql if not q.lstrip().startswith("SELECT")]


PASSWORD = "Mon1tor2Pass3word4"


def test_0022_without_a_password_creates_the_extension_and_no_role(monkeypatch) -> None:
    assert run(monkeypatch) == ["CREATE EXTENSION IF NOT EXISTS pg_stat_statements"]


def test_0022_with_a_password_creates_a_pg_monitor_login_and_nothing_more(monkeypatch) -> None:
    assert run(monkeypatch, PG_MONITOR_PASSWORD=PASSWORD) == [
        "CREATE EXTENSION IF NOT EXISTS pg_stat_statements",
        f"CREATE ROLE wcl_monitor LOGIN PASSWORD '{PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS",
        "GRANT pg_monitor TO wcl_monitor",
        'GRANT CONNECT ON DATABASE "wcl" TO wcl_monitor',
    ]


@pytest.mark.parametrize("password", ["short1", "it's:a-secret-password", "sixteen+chars-but-symbols", "abcdefghijklmno\\"])
def test_0022_refuses_a_password_that_is_not_16_letters_and_digits(monkeypatch, password: str) -> None:
    with pytest.raises(ValueError, match="letters and digits"):
        run(monkeypatch, PG_MONITOR_PASSWORD=password)


def test_0022_reuses_an_existing_monitor_only_role(monkeypatch) -> None:
    sql = run(monkeypatch, existing="", PG_MONITOR_PASSWORD=PASSWORD)
    assert not any(q.startswith("CREATE ROLE") for q in sql) and "GRANT pg_monitor TO wcl_monitor" in sql


@pytest.mark.parametrize("reasons", ["superuser", "bypassrls", "other memberships", "owns objects"])
def test_0022_refuses_an_existing_role_that_is_not_monitor_only(monkeypatch, reasons: str) -> None:
    with pytest.raises(RuntimeError, match="not monitor-only"):
        run(monkeypatch, existing=reasons, PG_MONITOR_PASSWORD=PASSWORD)
    with pytest.raises(RuntimeError, match="not monitor-only"):
        run(monkeypatch, "downgrade", existing=reasons)


@pytest.mark.parametrize("var", ["POSTGRES_USER", "APP_DB_USER"])
def test_0022_refuses_the_owner_or_runtime_role_as_monitor(monkeypatch, var: str) -> None:
    with pytest.raises(ValueError, match="owner or the runtime role"):
        run(monkeypatch, PG_MONITOR_USER="wcl_app", PG_MONITOR_PASSWORD=PASSWORD, **{var: "wcl_app"})


@pytest.mark.parametrize("name", ["wcl_monitor; DROP TABLE users", "Monitor", "x-y", "wcl_monitor\n"])
def test_0022_refuses_a_role_name_that_is_not_a_plain_identifier(monkeypatch, name: str) -> None:
    with pytest.raises(ValueError, match="identifier"):
        run(monkeypatch, PG_MONITOR_USER=name, PG_MONITOR_PASSWORD=PASSWORD)


# --- Postgres log masks (config.alloy, transform "postgres") ---------------------------------------

_OTTL_STRING = r'"((?:[^"\\]|\\.)*)"'


def _ottl(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def masks() -> list[tuple[str, set[str], object]]:
    """The body statements of the postgres transform as (kind condition, kinds, action): each
    replace_pattern and the withheld-detail rule, in order. Kinds are set by the stack."""
    alloy = ALLOY.read_text()
    block = alloy[alloy.index('otelcol.processor.transform "postgres"'):]
    block = block[:block.index("\n}\n")]
    out = []
    for stmt in re.findall(r"`((?:replace_pattern|set)\(body, .*?)`", block):
        kinds = set(re.findall(r'attributes\["alloy.pg_kind"\] == "(\w+)"', stmt))
        excluded = set(re.findall(r'attributes\["alloy.pg_kind"\] != "(\w+)"', stmt))
        if excluded:
            kinds = {"sql", "ops", "detail", "other"} - excluded
        args = [_ottl(a) for a in re.findall(_OTTL_STRING, stmt.split(" where ")[0])]
        if stmt.startswith("replace_pattern"):
            pattern, repl = args
            out.append((stmt, kinds, (re.compile(pattern), re.sub(r"\$\{(\d+)\}", r"\\g<\1>", repl))))
        else:
            keep = re.compile(_ottl(re.search(r'not IsMatch\(body, ' + _OTTL_STRING, stmt).group(1)))
            out.append((stmt, kinds, (keep, args[0])))
    return out


def mask(kind: str, body: str) -> str:
    for stmt, kinds, (pattern, repl) in masks():
        if kind not in kinds:
            continue
        if stmt.startswith("set("):
            body = body if pattern.search(body) else repl
        else:
            body = pattern.sub(repl, body)
    return body


ROW = ("Failing row contains (3f0c2a1e-9b7d-4c1e-8f3a-2d6b9e0a7c41, alice.smith@example.com, "
       "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$aGFzaGhhc2hoYXNo, active, f, null, 7).")


@pytest.mark.parametrize(("kind", "body", "want"), [
    ("detail", ROW, "Failing row contains (?)"),
    ("detail", "Failing row contains (a(b)c, (x), secret)) trailing.", "Failing row contains (?)"),
    ("detail", "Key (email)=(bob(work)@example.com) already exists.", "Key (email)=(?) already exists."),
    ("detail", "Key (tenant_id, code)=(42, a)b) is not present in table \"reports\".",
     "Key (tenant_id, code)=(?) is not present in table \"?\"."),
    ("detail", "Array value must start with \"{\" or dimension information: alice@example.com", "<detail withheld>"),
    ("detail", "Process holding the lock: 123. Wait queue: 456.", "Process holding the lock: ?. Wait queue: ?."),
    ("other", "duplicate key value violates unique constraint \"uq_users_email\"",
     "duplicate key value violates unique constraint \"?\""),
    ("other", "invalid input syntax for type uuid: \"alice-secret\"", "invalid input syntax for type uuid: \"?\""),
    ("sql", "execute s1: SELECT pg_sleep(0.8), 'hunter2' AS pw, 4242424242 AS id WHERE a = $1 /*traceparent='00-ab-cd-01'*/",
     "execute s1: SELECT pg_sleep(?), '?' AS pw, ? AS id WHERE a = $1 /*traceparent='?'*/"),
    ("ops", 'automatic vacuum of table "wcl.public.t": index scans: 0', 'automatic vacuum of table "wcl.public.t": index scans: 0'),
])
def test_postgres_log_masks(kind: str, body: str, want: str) -> None:
    assert mask(kind, body) == want


# --- dashboards and alert rules -------------------------------------------------------------------


def recorded(*files: str) -> set[str]:
    names = set()
    for path in RULES_DIR.glob("*.yaml") if not files else (RULES_DIR / f for f in files):
        for group in yaml.safe_load(path.read_text())["groups"]:
            names |= {rule["record"] for rule in group["rules"]}
    return names


def dashboard(name: str) -> dict:
    return json.loads((DASHBOARDS / name).read_text())


def panels(d: dict) -> list[dict]:
    return [q for p in d["panels"] for q in [p, *p.get("panels", [])]]


def mimir_targets(d: dict) -> list[tuple[dict, str]]:
    return [(p, t["expr"]) for p in panels(d) for t in p.get("targets", [])
            if (t.get("datasource") or p.get("datasource") or {}).get("uid") == "mimir"]


def test_d9_d10_d11_are_provisioned_with_their_uids() -> None:
    assert {p.name: dashboard(p.name)["uid"] for p in DASHBOARDS.glob("*.json")} == UIDS


@pytest.mark.parametrize("name", sorted(UIDS))
def test_every_mimir_query_reads_aliases_only(name: str) -> None:
    aliases = recorded()
    targets = mimir_targets(dashboard(name))
    assert targets
    for panel, expr in targets:
        used = metric_names(expr)
        assert used and used <= aliases, (panel["title"], used - aliases)
    # D10's comparison: Redis's own ratio next to the app's (056's cache:hit_ratio alias).
    if name == "redis.json":
        exprs = " ".join(e for p, e in mimir_targets(dashboard(name)) if p["title"].startswith("Hit ratio"))
        assert "redis:hit_ratio:5m" in exprs and "cache:hit_ratio" in exprs


@pytest.mark.parametrize("name", sorted(UIDS))
def test_query_shapes(name: str) -> None:
    for panel, expr in mimir_targets(dashboard(name)):
        # Aliases are already rates or gauges: no rate()/increase() on top of them.
        assert not re.search(r"\b(rate|irate|increase)\(", expr), (panel["title"], expr)
        # sc-471: per-interval bars or legend totals need a window equal to the step.
        custom = panel.get("fieldConfig", {}).get("defaults", {}).get("custom", {})
        calcs = panel.get("options", {}).get("legend", {}).get("calcs", [])
        if custom.get("drawStyle") == "bars" or {"sum", "total"} & set(calcs):
            windows = set(re.findall(r"\[([^\]]+)\]", expr))
            assert windows == {"$__interval"} and panel.get("interval"), (panel["title"], windows)
        if panel["type"] != "row":
            assert panel.get("fieldConfig", {}).get("defaults", {}).get("unit"), panel["title"]


def test_d9_lists_top_statements_and_the_knowledge_base_index() -> None:
    exprs: dict[str, list[str]] = {}
    for p, e in mimir_targets(dashboard("postgres.json")):
        exprs.setdefault(p["title"], []).append(e)
    assert exprs["Top statements by total time"] == ["topk(15, pg:statement_seconds:total)", "pg:statement_calls:total"]
    assert exprs["Knowledge-base index size"] == ["sum(pg:vector_index:bytes)"]
    logs = [t["expr"] for p in panels(dashboard("postgres.json")) for t in p.get("targets", [])
            if (t.get("datasource") or {}).get("uid") == "loki"]
    assert '{service_name="postgres"} | pg_duration_ms != ""' in logs


def test_d9_statement_panels_read_as_ids_and_busy_time() -> None:
    by_title = {p["title"]: p for p in panels(dashboard("postgres.json"))}
    table = by_title["Top statements by total time"]
    # queryid is a 64-bit id: unit "string" keeps Grafana from formatting it as a number (#77).
    queryid = [o for o in table["fieldConfig"]["overrides"] if o["matcher"] == {"id": "byName", "options": "queryid"}]
    assert queryid and {"id": "unit", "value": "string"} in queryid[0]["properties"]
    hidden = next(t for t in table["transformations"] if t["id"] == "organize")["options"]["excludeByName"]
    assert {"__name__", "__name__ 1", "__name__ 2"} <= {k for k, v in hidden.items() if v}
    # Seconds of execution per second is a busy fraction, not a per-call latency (unit "s").
    busy = by_title["Statement busy time by queryid"]
    assert busy["fieldConfig"]["defaults"]["unit"] == "suffix: s/s"


def test_d11_shows_drops_queue_ingest_and_series_against_the_budget() -> None:
    used = set().union(*(metric_names(e) for _, e in mimir_targets(dashboard("infra.json"))))
    assert {"meta:exporter_failures:increase2m", "meta:export_queue:ratio", "meta:ingest:rate5m",
            "meta:active_series:count", "meta:active_series:budget", "infra:container_cpu:rate5m",
            "infra:container_memory:bytes"} <= used
    budget = next(r for g in yaml.safe_load((RULES_DIR / "datastores.yaml").read_text())["groups"]
                  for r in g["rules"] if r["record"] == "meta:active_series:budget")
    assert budget["expr"] == "vector(50000)"


def test_alert_rules_read_aliases_and_the_threshold_is_one_rule() -> None:
    groups = yaml.safe_load(ALERTS.read_text())["groups"]
    rules = {r["uid"]: r for g in groups for r in g["rules"]}
    assert set(rules) == {"wcl-alert-pipeline", "wcl-alert-build-spend"}
    aliases = recorded()
    for rule in rules.values():
        queries = [d for d in rule["data"] if d["datasourceUid"] == "mimir"]
        assert queries and rule["noDataState"] == "OK"
        for q in queries:
            assert metric_names(q["model"]["expr"]) <= aliases, rule["uid"]
    spend = " ".join(q["model"].get("expr", q["model"].get("expression", "")) for q in rules["wcl-alert-build-spend"]["data"])
    assert "cc:cost_usd:rate5m[24h]" in spend and "alert:build_spend_usd_per_day:threshold" in spend
    assert "alert:build_spend_usd_per_day:threshold" in recorded("datastores.yaml")


# --- security pins ------------------------------------------------------------------------------


def test_only_cadvisor_holds_a_container_socket_and_it_is_hardened() -> None:
    compose = yaml.safe_load(COMPOSE.read_text())
    services = compose["services"]
    assert "docker-proxy" not in services
    for name, service in services.items():
        if name != "cadvisor":
            assert not any(".sock" in str(v) for v in service.get("volumes", [])), name
    cadvisor = services["cadvisor"]
    assert cadvisor["profiles"] == ["observability"] and "@sha256:" in cadvisor["image"]
    assert cadvisor["cap_drop"] == ["ALL"] and cadvisor["security_opt"] == ["no-new-privileges:true"]
    assert cadvisor["read_only"] is True and "ports" not in cadvisor and "privileged" not in cadvisor
    assert all(v.endswith(":ro") for v in cadvisor["volumes"])
    assert cadvisor["networks"] == ["cadvisor"] and compose["networks"]["cadvisor"]["internal"] is True
    # Postgres's log reaches Alloy as files on its own volume, read-only there.
    assert "pglog:/var/log/postgresql" in services["db"]["volumes"]
    assert "pglog:/var/log/postgresql:ro" in services["alloy"]["volumes"]
    assert "pglog" in compose["volumes"]


def test_alloy_section_keeps_keys_sql_and_secrets_out() -> None:
    alloy = ALLOY.read_text()
    section = alloy[alloy.index("// --- Data stores and infra (feature 058) ---"):]
    assert not re.search(r"(discovery|loki\.source)\.docker|docker\.sock|docker-proxy", section)
    assert '"__path__" = "/var/log/postgresql/postgresql-*.log"' in section and "check_keys" not in section
    assert re.search(r"include_query\s*=\s*false", section)
    assert 'sys.env("WCL_PG_MONITOR_DSN")' in section and "postgresql://" not in section
    # Postgres's log goes through the redaction chain, never straight to a Loki writer.
    assert "loki.write" not in section
    postgres = section[section.index('otelcol.processor.transform "postgres"'):]
    assert re.search(r"output \{\s*logs = \[otelcol\.processor\.memory_limiter\.default\.input\]", postgres)
    db = yaml.safe_load(COMPOSE.read_text())["services"]["db"]["command"]
    assert "log_parameter_max_length=0" in db and "pg_stat_statements.track_utility=off" in db
    assert {"logging_collector=on", "log_directory=/var/log/postgresql", "log_truncate_on_rotation=on"} <= set(db)


def _relabel_filters(project: str) -> list[tuple[str, list[str], re.Pattern]]:
    """The keep/drop rules of prometheus.relabel "datastores" as (action, source labels, regex),
    with WCL_COMPOSE_PROJECT set to `project`; Prometheus anchors relabel regexes at both ends."""
    alloy = ALLOY.read_text()
    block = alloy[alloy.index('prometheus.relabel "datastores"'):]
    block = block[:block.index("\n}\n")]
    rules = []
    for body in re.findall(r"rule \{(.*?)\n  \}", block, re.S):
        action = re.search(r'action\s*=\s*"(\w+)"', body)
        if not action or action[1] not in {"keep", "drop"}:
            continue
        labels = re.findall(r'"([^"]+)"', re.search(r"source_labels\s*=\s*\[(.*?)\]", body, re.S)[1])
        expr = re.search(r"regex\s*=\s*(.*)", body)[1].replace('sys.env("WCL_COMPOSE_PROJECT")', json.dumps(project))
        if expr.startswith("string.join"):  # the __name__ allowlist
            names = re.findall(r'"((?:[^"\\]|\\.)*)"', body)
            regex = "|".join(names[1:-1])
        else:
            regex = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', expr))
        rules.append((action[1], labels, re.compile(f"(?:{regex})")))
    return rules


def _kept(project: str, **series: str) -> bool:
    for action, labels, regex in _relabel_filters(project):
        hit = regex.fullmatch(";".join(series.get(label, "") for label in labels)) is not None
        if hit != (action == "keep"):
            return False
    return True


@pytest.mark.parametrize("project", ["wcl-obs-ansel", ""])
def test_cadvisor_keeps_the_host_and_this_project_only(project: str) -> None:
    cpu = {"__name__": "container_memory_working_set_bytes", "job": "cadvisor"}
    # The root cgroup is the host line of D11 (BUG-001: it used to be dropped).
    assert _kept(project, **cpu, id="/")
    # Other projects' containers and unlabelled cgroups go, also with the project unset.
    assert not _kept(project, **cpu, id="/system.slice/docker-1.scope", container_label_com_docker_compose_project="other")
    assert not _kept(project, **cpu, id="/system.slice/ssh.service")
    assert not _kept(project, **cpu, id="system.slice")
    assert _kept(project, **cpu, id="/system.slice/docker-2.scope",
                 container_label_com_docker_compose_project=project) == bool(project)


def test_claude_code_streams_are_summed_after_their_ids_are_dropped() -> None:
    """Board #76: without the sum, the streams of one export share labels and timestamp and Mimir
    silently discards all but one (datastores.sh proves the values on the stack)."""
    alloy = ALLOY.read_text()
    block = alloy[alloy.index('otelcol.processor.transform "metric_labels"'):]
    block = block[:block.index("\n}\n")]
    delete = block.index('context    = "datapoint"')
    total = block.index('`aggregate_on_attributes("sum") where resource.attributes["service.name"] == "claude-code"`')
    assert delete < total and 'context    = "metric"' in block[delete:total]
