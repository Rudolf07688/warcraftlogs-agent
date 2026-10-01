"""
Example consumer showing how to read the mimicked CDC events.
This is EXACTLY how you'd consume real Debezium events too —
that's the whole point of mimicking the envelope shape.
"""

import asyncio
import json
from aiokafka import AIOKafkaConsumer


async def consume_orders():
    consumer = AIOKafkaConsumer(
        "cdc.public.orders",
        bootstrap_servers="localhost:9092",
        group_id="orders-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")) if v else None,
        key_deserializer=lambda k: json.loads(k.decode("utf-8")) if k else None,
    )
    await consumer.start()
    try:
        async for msg in consumer:
            # Tombstone check — MUST handle null value (real Debezium behavior)
            if msg.value is None:
                print(f"[TOMBSTONE] key={msg.key}")
                await consumer.commit()
                continue

            envelope = msg.value
            op = envelope["op"]
            before = envelope["before"]
            after = envelope["after"]
            source = envelope["source"]

            if op == "c":
                print(f"[INSERT] table={source['table']} row={after}")
            elif op == "u":
                print(f"[UPDATE] table={source['table']} before={before} after={after}")
            elif op == "d":
                print(f"[DELETE] table={source['table']} row={before}")
            elif op == "r":
                print(f"[SNAPSHOT] table={source['table']} row={after}")

            await consumer.commit()
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(consume_orders())
