# Kafka Streaming — Extended Reference

## Parquet Sink from Kafka

Kafka is optimized for low-latency event transport, while Parquet is optimized for columnar analytics and cheap long-term storage. The recommended pattern is to keep events in Kafka in an event-native format, then materialize Parquet in downstream storage.

### Recommended flow

1. FastAPI producer publishes JSON events to Kafka.
2. Kafka Connect, Flink, Spark Structured Streaming, or a custom consumer reads the topic.
3. The sink batches records and writes Parquet files to object storage.
4. Query engines such as Spark, Trino, DuckDB, BigQuery, or Athena read the Parquet dataset.

```text
FastAPI -> Kafka topic -> Sink connector / stream job -> Parquet files in object storage -> Analytics
```

### Why Parquet belongs downstream

- Columnar storage reduces scan cost for analytics workloads.
- Compression is strong, especially for repeated columns and typed data.
- Predicate pushdown and column pruning make it ideal for BI and lakehouse queries.
- It is not well suited as a per-event wire format for HTTP-driven producers.

### Dataset design guidance

- Partition by time first for predictable pruning, for example `year/month/day/hour`.
- Add low-to-medium cardinality business partitions only when they improve query locality.
- Avoid high-cardinality folder partitioning such as `customer_id=<millions>`.
- Keep file sizes healthy, typically tens to hundreds of MB per Parquet file, to avoid small-file problems.
- Prefer schema-managed tables with Iceberg or Delta Lake when evolution and compaction matter.

### Common sink options

- Kafka Connect S3 Sink / GCS Sink / Azure Blob Sink.
- Spark Structured Streaming jobs reading Kafka and writing Parquet.
- Flink SQL or Flink DataStream jobs for streaming enrichment before Parquet output.

### Practical producer rule

For your dummy FastAPI producer, keep the event payload JSON unless you already have a strong binary-format requirement. Put Parquet concerns in the downstream data platform path, not inside the producer itself.

## Transactional Producer (Exactly-Once)

Use when publishing to multiple topics atomically (e.g., Kafka Streams, outbox pattern).

```python
producer = AIOKafkaProducer(
    bootstrap_servers=settings.kafka_bootstrap_servers,
    transactional_id="order-service-tx-1",
    enable_idempotence=True,
    acks="all",
)
await producer.start()

async with producer.transaction():
    await producer.send("orders.created", value=order_event)
    await producer.send("inventory.reserved", value=inventory_event)
# Both committed atomically, or neither
```

**Requirements for transactional topics:**
- `replication.factor >= 3`
- `min.insync.replicas = 2`
- Consumers must set `isolation.level=read_committed`

## Outbox Pattern (Reliable Event Publishing)

Prevents the dual-write problem (DB write + Kafka publish not atomic).

1. Write domain event to an `outbox` table in the same DB transaction as your entity.
2. Debezium CDC picks up the `outbox` table change and publishes to Kafka.
3. Mark the outbox row as published.

This guarantees the event is published if and only if the DB transaction commits.

```sql
CREATE TABLE outbox (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  aggregate_type TEXT NOT NULL,  -- e.g. 'Order'
  aggregate_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  published BOOLEAN DEFAULT FALSE
);
```

Use Debezium's `outbox event router` SMT (Single Message Transform) to route events to
the correct topic based on `aggregate_type`.

## Consumer Group Management

```python
from aiokafka import AIOKafkaConsumer

consumer = AIOKafkaConsumer(
    "orders.created",
    bootstrap_servers=settings.kafka_bootstrap_servers,
    group_id="order-processor",
    auto_offset_reset="earliest",
    enable_auto_commit=False,        # manual commit for reliability
    max_poll_records=100,
    session_timeout_ms=30_000,
    heartbeat_interval_ms=10_000,
)

await consumer.start()
try:
    async for msg in consumer:
        try:
            await process_message(msg)
            await consumer.commit()  # commit after successful processing
        except ProcessingError:
            await send_to_dlq(msg)
            await consumer.commit()  # still commit — don't reprocess poison messages
finally:
    await consumer.stop()
```

## Graceful Shutdown for Consumer

```python
import asyncio, signal

shutdown_event = asyncio.Event()

def handle_signal():
    shutdown_event.set()

loop = asyncio.get_event_loop()
loop.add_signal_handler(signal.SIGTERM, handle_signal)
loop.add_signal_handler(signal.SIGINT, handle_signal)

# In consumer loop:
while not shutdown_event.is_set():
    try:
        msg = await asyncio.wait_for(consumer.__anext__(), timeout=1.0)
        await process(msg)
    except asyncio.TimeoutError:
        continue  # check shutdown_event
```

## Saga Pattern with Kafka

For distributed transactions across microservices:

1. **Choreography Saga**: Each service listens to events and emits its own.
   - `OrderService` emits `orders.created`
   - `InventoryService` listens, reserves stock, emits `inventory.reserved`
   - `PaymentService` listens, charges, emits `payments.completed`
   - On failure, each service emits a compensating event.

2. **Orchestration Saga**: A dedicated saga orchestrator service coordinates steps via commands.

Key consideration: Each step must be idempotent and handle compensating transactions.

## Multi-Tenancy Topic Patterns

```
{tenant}.{domain}.{entity}.{event_type}
tenantA.orders.created
tenantB.payments.processed

# Or namespace by environment
prod.orders.created
staging.orders.created
```

## Consumer Lag Monitoring (Python)

```python
from confluent_kafka.admin import AdminClient
from confluent_kafka import Consumer

admin = AdminClient({"bootstrap.servers": "localhost:9092"})

def get_consumer_lag(topic: str, group_id: str) -> dict:
    consumer = Consumer({
        "bootstrap.servers": "localhost:9092",
        "group.id": group_id,
    })
    partitions = consumer.list_topics(topic).topics[topic].partitions
    lag = {}
    for partition_id in partitions:
        tp = TopicPartition(topic, partition_id)
        committed = consumer.committed([tp])[0].offset
        low, high = consumer.get_watermark_offsets(tp)
        lag[partition_id] = high - committed
    consumer.close()
    return lag
```
