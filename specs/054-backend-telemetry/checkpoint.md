# Checkpoint 054 (2026-11-04)

Decisions: board keys scope:054:redaction-placement, scope:054:lockdown, scope:054:off,
scope:054:oneshot-content; open question owner:backend/app/api/ws.py (per-turn root span).
Deps added (T001 done, uncommitted). Implementation starts at T003 (telemetry/config.py), then
setup.py, policy.py, redaction.py, the main.py bootstrap call before `from fastapi import FastAPI`.
Key facts: backend.app.config imports ADK → bootstrap reads env itself; ADK content env is read
per TelemetryConfig construction from os.environ; ProxyTracer caches the real tracer → tests
disable SDK tracers on teardown via _set_tracer_configurator.
