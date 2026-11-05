---
id: otel-test-providers
anchors: [file:backend/tests/test_telemetry_support.py, file:backend/tests/test_telemetry_bootstrap.py]
by: dev-3 Nils
source: meta/team/dev-3.md L20
verified: b9cf9a3 2026-11-05
---
OTel global providers can be set only once per process, so the telemetry tests share one
provider with swappable processors: set `test_telemetry_support._SPANS.target` /
`_LOGS.target` to a capture. Test a global patch (`instrument()`) in a fresh interpreter.
The `PROBE` script in `test_telemetry_bootstrap.py` runs the real app bootstrap, so pin
bootstrap behaviour there.
