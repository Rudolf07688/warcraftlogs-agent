"""The backend path of redaction_e2e.py (feature 060, sc-423): the real telemetry bootstrap.

Run by redaction_e2e.py in a clean environment with OTEL_EXPORTER_OTLP_ENDPOINT pointing at the
test stack's Alloy. Reads ``{"marker": ..., "texts": {shape: text}}`` on stdin, turns telemetry
on exactly as main.py does (``configure_telemetry`` and ``otlp_log_handler``), and puts every
seeded text into a span attribute, a span event attribute, a log record (message and an
``extra`` field, through the root logger's OTLP handler) and an allowlisted metric attribute.
The resource carries them too, through OTEL_RESOURCE_ATTRIBUTES (set by the caller). Prints the
trace id; the SDK's exit hook flushes all three signals.

    uv run python observability/test/redaction_e2e_backend.py < seeds.json
"""

from __future__ import annotations

import json
import logging
import sys

from backend.app.telemetry import configure_telemetry, otlp_log_handler

seeds = json.load(sys.stdin)
marker, texts = seeds["marker"], seeds["texts"]
if configure_telemetry() is None:
    sys.exit("telemetry is off: OTEL_EXPORTER_OTLP_ENDPOINT is not set")

from opentelemetry import metrics, trace  # noqa: E402 - after the providers are installed

handler = otlp_log_handler()
root = logging.getLogger()
root.addHandler(handler)
root.setLevel(logging.INFO)
log = logging.getLogger("wcl.redaction_e2e")

counter = metrics.get_meter("redaction-e2e").create_counter("app.redaction_e2e")
with trace.get_tracer("redaction-e2e").start_as_current_span(f"{marker}-span") as span:
    for shape, text in texts.items():
        span.set_attribute(f"seed.{shape}", text)
        span.add_event("seed.event", {f"seed.{shape}": text})
        log.warning("%s log %s: %s", marker, shape, text, extra={"seed_field": text})
        # app.cache.name is on the meter view's allowlist (setup.METRIC_ATTRIBUTES), so the
        # value reaches Alloy; Alloy's datapoint rules are what must mask it.
        counter.add(1, {"app.cache.name": text})
    print(format(span.get_span_context().trace_id, "032x"))
