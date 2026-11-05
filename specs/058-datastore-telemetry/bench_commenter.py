"""Micro-benchmark: what the sqlcommenter traceparent comment costs per statement (feature 058).

Run once per variant (instrumentation patches globally, so each variant is its own process):
    uv run python specs/058-datastore-telemetry/bench_commenter.py URL VARIANT [N]
VARIANT: off | spans | commenter | commenter-nocache
Each statement runs inside its own recording span (like a request), against a throwaway Postgres
(pg.py up). Prints the median and p95 per-statement latency in microseconds.
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import text

SQL = text("SELECT oid, relname FROM pg_class WHERE relname = :name AND relnamespace = :ns")


async def main(url: str, variant: str, n: int) -> None:
    trace.set_tracer_provider(TracerProvider())
    if variant != "off":
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        options = {"skip_dep_check": True}
        if variant.startswith("commenter"):
            options |= {"enable_commenter": True, "commenter_options": {"db_driver": False, "db_framework": False}}
        SQLAlchemyInstrumentor().instrument(**options)
    # Imported after instrument(), as in the app (main.py configures telemetry first): the
    # instrumentor wraps create_async_engine, so a name bound earlier stays unpatched.
    from sqlalchemy.ext.asyncio import create_async_engine

    if variant == "commenter-nocache":
        url += "?prepared_statement_cache_size=0"
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    tracer = trace.get_tracer("bench")
    samples = []
    async with engine.connect() as conn:
        for i in range(n + 200):
            with tracer.start_as_current_span("request"):
                start = time.perf_counter()
                await conn.execute(SQL, {"name": "pg_class", "ns": 11})
                elapsed = time.perf_counter() - start
            if i >= 200:  # warm-up
                samples.append(elapsed * 1e6)
    await engine.dispose()
    samples.sort()
    print(f"{variant:18s} n={n} median={statistics.median(samples):7.1f}us p95={samples[int(0.95 * n)]:7.1f}us")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 3000))
