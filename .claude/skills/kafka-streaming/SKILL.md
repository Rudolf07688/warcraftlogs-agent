---
name: kafka-streaming
description: >
  Kafka streaming best practices for Python/FastAPI services — covering producer design
  (aiokafka singleton via lifespan, confluent-kafka for sync/multi-threaded contexts),
  topic naming conventions, partition strategy, durability settings (acks, idempotence,
  compression), serialisation (JSON → Avro/Schema Registry path), and Change Data Capture
  (CDC) with Debezium + Kafka Connect. Use when building Kafka producers or consumers in
  FastAPI, designing topics, or setting up CDC pipelines from PostgreSQL/MySQL to Kafka.
license: MIT
metadata:
  author: internal
  version: "1.0"
  domain: kafka, streaming, fastapi, cdc, debezium
compatibility: Python 3.11+, FastAPI 0.100+, aiokafka 0.10+, confluent-kafka 2.x, Debezium 2.x
---

# Kafka Streaming Best Practices

## 1. Choosing a Python Kafka Client

| Library | Async | Thread-safe | Best for |
|---------|-------|-------------|----------|
| `aiokafka` | ✅ native asyncio | ✅ within single event loop | **FastAPI** (recommended) |
| `confluent-kafka` | ❌ (wrap manually) | ✅ across threads | sync services, multi-threaded workers, Celery |
| `kafka-python` | ❌ | ⚠️ | legacy only — not actively maintained |

**Rule:** Use `aiokafka` for FastAPI. Use `confluent-kafka` if you mix `asyncio` with threading.

---

## 2. FastAPI Producer — Singleton via Lifespan

**Critical rules:**
- Create one `AIOKafkaProducer` instance at startup; never instantiate per-request.
- Use the `lifespan` context manager (avoid deprecated `@app.on_event`).
- Store the producer on `app.state` and surface it via a dependency.
- Call `await producer.stop()` on shutdown — omitting this loses in-flight messages.

```python
# app/kafka/producer.py
from aiokafka import AIOKafkaProducer
from app.config import settings
import json

_producer: AIOKafkaProducer | None = None

async def start_producer() -> AIOKafkaProducer:
    global _producer
    _producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",                      # wait for all ISR replicas
        enable_idempotence=True,         # exactly-once at producer level (Kafka 3.0+ default)
        compression_type="lz4",          # good balance of speed and ratio
        linger_ms=5,                     # batch window — trade 5ms latency for 10x fewer requests
        max_in_flight_requests_per_connection=5,  # safe with idempotence enabled
        request_timeout_ms=30_000,
        retry_backoff_ms=100,
    )
    await _producer.start()
    return _producer

async def stop_producer():
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None

def get_producer() -> AIOKafkaProducer:
    if _producer is None:
        raise RuntimeError("Kafka producer not initialised")
    return _producer
```

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.kafka.producer import start_producer, stop_producer

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.kafka_producer = await start_producer()
    yield
    await stop_producer()

app = FastAPI(lifespan=lifespan)
```

```python
# app/dependencies.py
from fastapi import Request
from aiokafka import AIOKafkaProducer

def get_kafka_producer(request: Request) -> AIOKafkaProducer:
    return request.app.state.kafka_producer
```

```python
# app/routers/orders.py
from fastapi import APIRouter, Depends, status
from aiokafka import AIOKafkaProducer
from app.dependencies import get_kafka_producer
from app.models import OrderCreatedEvent

router = APIRouter()

@router.post("/orders", status_code=status.HTTP_202_ACCEPTED)
async def create_order(
    payload: OrderCreatedEvent,
    producer: AIOKafkaProducer = Depends(get_kafka_producer),
):
    await producer.send(
        topic="orders.created",
        key=str(payload.order_id),   # route same order to same partition
        value=payload.model_dump(),
    )
    return {"status": "queued"}
```

> **Fire-and-forget vs awaited send:** `producer.send(...)` is fire-and-forget (buffered).
> Use `await producer.send_and_wait(...)` when you need delivery confirmation before responding.
> For most API endpoints, fire-and-forget + idempotence is correct.

---

## 3. Producer Configuration Reference

| Config | Default | Recommended (prod) | Why |
|--------|---------|--------------------|-----|
| `acks` | `1` | `"all"` | Waits for all ISR replicas — required for durability |
| `enable_idempotence` | `True` (Kafka 3+) | `True` | Prevents duplicates on retry |
| `compression_type` | `none` | `lz4` | ~3x compression, minimal CPU overhead |
| `linger_ms` | `0` | `5–20` | Batches messages; reduces network calls ~10x |
| `batch_size` | `16384` | `32768–65536` | Larger batches improve throughput |
| `max_in_flight_requests_per_connection` | `5` | `5` | Safe max with idempotence |
| `retries` | `0` | `Integer.MAX_VALUE` (auto with idempotence) | Retry transient failures |
| `delivery_timeout_ms` | `120000` | `120000` | Total time before giving up on a send |

---

## 4. Topic Naming Conventions

Use a structured dot-separated hierarchy:

```
{domain}.{entity}.{event_type}[.{version}]
```

**Examples:**
```
orders.created
orders.cancelled.v2
payments.processed
users.registered
inventory.updated
cdc.public.orders          # CDC topics: {prefix}.{schema}.{table}
```

**Rules:**
- All lowercase; use dots (`.`) or hyphens (`-`), never mix.
- No spaces, underscores in the primary name hierarchy.
- Prefix CDC topics: `cdc.<schema>.<table>` — Debezium default.
- Avoid generic names: `data`, `events`, `messages` — they give no context.
- Include version suffix when breaking changes are possible: `orders.created.v2`.
- Max 249 characters.
- Prefix test/integration topics: `it-<uuid>-<description>`.

---

## 5. Partition Strategy

| Scenario | Recommended approach |
|----------|----------------------|
| Order guarantee within entity (e.g., same order) | Use entity ID as partition key |
| Maximum throughput, no ordering needed | Round-robin (null key) |
| Skewed traffic by region/tenant | Composite key or custom partitioner |
| Time-series with time-based key | Avoid pure timestamps as keys — causes hot partitions during peak hours |

**Partition count guidance (2025+, KRaft/no ZooKeeper):**
- Dev/test: 3–6 partitions
- Production: **12–30 partitions** (old conservative 6–12 was ZooKeeper-limited)
- Formula: `partitions ≥ ceil(target_throughput / single_consumer_throughput)`
- More partitions = more consumer parallelism, but adds replication overhead

**Replication factor:**
- Dev: 1 (single broker)
- Production: **3** (standard) with `min.insync.replicas=2`

---

## 6. Message Serialisation

**For MVP/dev:** JSON is fine.

```python
value_serializer=lambda v: json.dumps(v).encode("utf-8")
```

**For production analytics / lakehouse flows:** prefer Parquet on the downstream sink side.
- Kafka remains stream-optimized and row-oriented; Parquet is best at the storage and analytics edge.
- Keep producer payloads simple (JSON for MVP, or compact binary if needed), then use a sink to land partitioned Parquet files in object storage.
- Common pattern: Kafka topic -> Kafka Connect sink -> S3/GCS/Azure Blob -> Parquet dataset -> Spark/Trino/DuckDB/BigQuery.
- Partition Parquet datasets by time and stable business dimensions, for example: `year=2026/month=07/day=09/domain=orders/`.
- Enforce schema contracts in the sink/lakehouse layer with Iceberg, Delta Lake, Hive Metastore, Glue Catalog, or warehouse table definitions.
- Do **not** try to make Parquet your producer wire format for request/response event publishing; it is a batch/analytic file format, not an event-native transport format.

```yaml
# Typical sink-oriented flow
producer:
  format: json
  topic: orders.created
sink:
  input_topic: orders.created
  output_format: parquet
  destination: s3://company-lake/orders/
```

See `references/REFERENCE.md` for Parquet sink patterns and lakehouse guidance.

---

## 7. Error Handling Patterns

### Dead Letter Queue (DLQ)
Send unprocessable events to a `<topic>.dlq` topic instead of blocking the partition.

```python
async def safe_publish(producer, topic: str, key: str, value: dict):
    try:
        await producer.send_and_wait(topic, key=key, value=value)
    except Exception as exc:
        # Log and route to DLQ — never crash the API
        logger.error("Kafka send failed", topic=topic, error=str(exc))
        await producer.send(f"{topic}.dlq", key=key, value={
            "original": value, "error": str(exc), "ts": time.time()
        })
```

### Consumer Idempotency
Kafka guarantees **at-least-once** delivery with `acks=all` + retries.
Design consumers to be idempotent — track processed event IDs in Redis or DB:

```python
if await redis.get(f"processed:{event_id}"):
    return  # deduplicate
await process(event)
await redis.setex(f"processed:{event_id}", 86400, "1")
```

---

## 8. CDC with Debezium — Architecture Overview

```
PostgreSQL WAL  →  Debezium Connector  →  Kafka Connect  →  Kafka Topics  →  Consumers
(transaction log)  (reads binlog/WAL)    (distributed)    (one per table)
```

**When to use CDC:**
- Multiple downstream systems need the same DB changes in real-time.
- You cannot modify application code to emit events.
- You need deletes captured (impossible with query-based polling).
- Audit trail, cache invalidation, search index sync, event sourcing.

**Debezium vs JDBC Source Connector:**

| | Debezium (log-based) | JDBC Source Connector |
|-|-|-|
| Captures deletes | ✅ | ❌ |
| Latency | Sub-second | Bounded by poll interval |
| DB impact | Near-zero (reads WAL) | Periodic SELECT load |
| Setup complexity | Medium | Low |
| Use for | **Most production cases** | Append-only tables, quick prototypes |

---

## 9. CDC Setup — PostgreSQL + Debezium

### 9.1 PostgreSQL configuration

```sql
-- postgresql.conf
wal_level = logical
max_replication_slots = 4
max_wal_senders = 4
```

```sql
-- Create dedicated replication user (least privilege)
CREATE ROLE debezium WITH REPLICATION LOGIN PASSWORD 'strong_password';
GRANT USAGE ON SCHEMA public TO debezium;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO debezium;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO debezium;

-- Create publication for tracked tables only
CREATE PUBLICATION dbz_publication FOR TABLE orders, customers, products;
```

### 9.2 Kafka Connect + Debezium (docker-compose snippet)

```yaml
kafka-connect:
  image: debezium/connect:2.5
  ports:
    - "8083:8083"
  environment:
    BOOTSTRAP_SERVERS: kafka:9092
    GROUP_ID: connect-cluster
    CONFIG_STORAGE_TOPIC: connect-configs
    OFFSET_STORAGE_TOPIC: connect-offsets
    STATUS_STORAGE_TOPIC: connect-status
    KEY_CONVERTER: org.apache.kafka.connect.json.JsonConverter
    VALUE_CONVERTER: org.apache.kafka.connect.json.JsonConverter
  depends_on:
    - kafka
    - postgres
```

### 9.3 Register the connector

```json
{
  "name": "pg-cdc-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "dbz_password",
    "database.dbname": "app_db",
    "topic.prefix": "cdc",
    "schema.include.list": "public",
    "table.include.list": "public.orders,public.customers",
    "publication.name": "dbz_publication",
    "slot.name": "debezium_slot",
    "plugin.name": "pgoutput",
    "snapshot.mode": "initial",
    "tombstones.on.delete": "true",
    "heartbeat.interval.ms": "10000",
    "key.converter.schemas.enable": "false",
    "value.converter.schemas.enable": "false"
  }
}
```

```bash
curl -X POST http://localhost:8083/connectors \
  -H "Content-Type: application/json" \
  -d @pg-cdc-connector.json

# Check status
curl -s http://localhost:8083/connectors/pg-cdc-connector/status | jq .
```

---

## 10. CDC Event Envelope (Debezium)

Topics follow `{prefix}.{schema}.{table}` → e.g., `cdc.public.orders`

```json
{
  "before": null,
  "after": {
    "id": 1001,
    "customer_id": 1,
    "total": 149.97
  },
  "source": {
    "connector": "postgresql",
    "db": "app_db",
    "schema": "public",
    "table": "orders",
    "lsn": 234567890,
    "txId": 5678,
    "ts_ms": 1704067200000
  },
  "op": "c",
  "ts_ms": 1704067200123
}
```

| `op` value | Meaning | `before` | `after` |
|------------|---------|----------|---------|
| `c` | INSERT | `null` | full row |
| `u` | UPDATE | full row | full row |
| `d` | DELETE | full row | `null` |
| `r` | READ (snapshot) | `null` | full row |

**Always handle the tombstone:** after a delete, Debezium emits a second message with `null` value (required for log compaction). Consumers must not crash on null payload.

---

## 11. CDC Operational Pitfalls

| Pitfall | Cause | Fix |
|---------|-------|-----|
| WAL/replication slot growth | Consumer lag or stopped connector | Monitor `pg_replication_slots`; set `max_slot_wal_keep_size` |
| Schema evolution breaks consumers | Added/removed column in source table | Use Schema Registry with backward compatibility enforcement |
| Snapshot overload | Large existing table on first start | Use `snapshot.mode=no_data` if only future changes needed, or throttle |
| Out-of-order events across tables | Multi-partition consumption | Handle ordering in consumer logic; single-partition = ordering but limits throughput |
| Tombstone crashes consumer | Null value on delete event | Check `msg.value() is not None` before deserialising |
| Connector silent `FAILED` state | Network partition, schema change | Monitor connector status; set up Prometheus alerts or auto-restart policy |

**Heartbeat configuration** (prevents replication slot growth during idle periods):
```json
"heartbeat.interval.ms": "10000",
"heartbeat.action.query": "UPDATE public.debezium_heartbeat SET ts = now() WHERE id = 1"
```

---

## 12. Observability & Monitoring

### Key producer metrics (aiokafka)
```python
# Access via producer.metrics()
# record-send-rate     — events/sec
# record-error-rate    — failed sends/sec
# request-latency-avg  — broker round-trip ms
```

### Key consumer metrics
- `records-lag-max` — **critical**: rising lag = consumer falling behind
- `records-consumed-rate` — events/sec
- `commit-latency-avg` — offset commit time

### Connector health (CDC)
```bash
# Check all connectors
curl -s http://localhost:8083/connectors?expand=status | jq '.[].status.connector.state'

# Alert when any task is not RUNNING
```

### Recommended stack
- **Kafka UI** (dev): `provectuslabs/kafka-ui` — visual topic/consumer/connector browser
- **Prometheus + Grafana**: JMX exporter for broker metrics; Kafka Overview dashboard
- **Structured logging**: include `topic`, `partition`, `offset`, `event_id` in every log line

---

## 13. Production Checklist

### Producer (FastAPI)
- [ ] Singleton producer via `lifespan`, stored on `app.state`
- [ ] `acks="all"` + `enable_idempotence=True`
- [ ] `compression_type="lz4"` or `"zstd"`
- [ ] Partition key set (entity ID) for ordering guarantees
- [ ] DLQ topic for failed sends
- [ ] Graceful shutdown (`await producer.stop()`)
- [ ] Integration tests with Testcontainers

### Topics
- [ ] Explicit topic creation (disable `auto.create.topics.enable` in prod)
- [ ] Replication factor ≥ 3, `min.insync.replicas=2`
- [ ] Retention configured (`log.retention.hours` or `log.retention.bytes`)
- [ ] 12–30 partitions for high-throughput production topics

### CDC (Debezium)
- [ ] Dedicated `debezium` DB user with minimal privileges
- [ ] `snapshot.mode=initial` for first run; switch to `no_data` if only changes needed
- [ ] `heartbeat.interval.ms` set to prevent WAL growth
- [ ] `tombstones.on.delete=true` for log-compacted topics
- [ ] Schema Registry with backward compatibility enforced
- [ ] Monitor `pg_replication_slots` for slot growth
- [ ] Connector auto-restart policy or alerting on FAILED state
- [ ] Consumers handle `op` types: `c`, `u`, `d`, `r`, and null tombstones

---

## 14. Local Dev Stack (docker-compose)

See `assets/docker-compose.kafka.yml` for a ready-to-use local stack including:
- Kafka (KRaft mode, single broker)
- Kafka UI on `:8080`
- Kafka Connect + Debezium on `:8083`
- Schema Registry on `:8081`

```bash
docker compose -f assets/docker-compose.kafka.yml up -d
# Create a topic
docker exec kafka kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic orders.created --partitions 6 --replication-factor 1
# Tail a topic
docker exec kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic orders.created --from-beginning
```

See `references/REFERENCE.md` for advanced patterns: Avro serialisation, transactional producers, consumer group management, Saga pattern with Kafka.

