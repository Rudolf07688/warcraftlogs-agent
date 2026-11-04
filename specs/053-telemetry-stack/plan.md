# Implementation Plan: Telemetry stack, claude-otel wrapper, Alloy redaction

**Branch**: `053-telemetry-stack` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

## Summary

Add Grafana Alloy to `docker-compose.yml` as an always-on collector and an `observability`
profile with Loki, Tempo, Mimir and Grafana. Alloy receives OTLP, stamps resource defaults,
redacts secrets (OTTL), strips banned metric labels, routes content logs to a 7-day Loki
stream, and exports through persistent, size-bounded queues. Grafana datasources are
provisioned with correlations. `bin/claude-otel` wraps Claude Code with the §5.2 env.
Shell test scripts prove persistence, redaction and provisioning against a throwaway
compose project.

## Technical Context

**Language/Version**: Alloy configuration syntax, YAML, Bash (no Python change)
**Primary Dependencies**: grafana/alloy v1.21.3, loki 3.7.9, tempo 2.10.10, mimir 3.2.4, grafana 13.2.5
**Storage**: named volumes `alloy-data`, `loki-data`, `tempo-data`, `mimir-data`, `grafana-data`
**Testing**: `observability/test/*.sh` (curl OTLP/HTTP JSON in, backend HTTP APIs out); `check.py run` for the untouched Python suite
**Target Platform**: Linux Docker Compose, local dev
**Constraints**: loopback ports overridable by env; `mem_limit` per service (Alloy 512m, Loki 512m, Tempo 512m, Mimir 1g, Grafana 256m); no MinIO, no Pyroscope, no dashboards
**Scale/Scope**: one developer machine; under 50k active series

## Constitution Check

- I reuse: official images and their documented config; no new code beyond a wrapper and test scripts. Pass.
- II small verified steps: each story has its own script run against live containers. Pass.
- III simplest design: one Alloy file, monolithic backends on local disk, transform-only redaction. Pass.
- IV/V (typed boundaries, async FastAPI): no Python touched. N/A.
- VIII Shortcut: sc-398..401 In Progress, Under Review at hand-off.

## Project Structure

```text
docker-compose.yml                      # alloy (always) + observability profile services; backend OTEL env
bin/claude-otel                         # wrapper (sc-400)
observability/
  README.md
  alloy/config.alloy                    # receive, stamp, redact, label hygiene, content routing, queues
  loki/loki.yaml                        # OTLP label allowlist, retention + content retention_stream
  tempo/tempo.yaml                      # 7d block retention, metrics-generator off
  mimir/mimir.yaml                      # monolithic, filesystem, 13-month retention, OTLP promotion, exemplars
  grafana/provisioning/datasources/datasources.yaml   # correlations (sc-399)
  test/lib.sh                           # shared helpers (compose wrapper, OTLP senders, pollers)
  test/persistence.sh                   # sc-398
  test/redaction.sh                     # sc-401
  test/provisioning.sh                  # sc-399
  test/claude-otel.sh                   # sc-400 (stub claude)
```

Spec §11 suggests `docker-compose.observability.yml` and Alloy modules; the brief names
`docker-compose.yml` as the file and one config file is enough this sprint (III).

## Risks

- Public-preview file storage: pinned image, flag verified at startup.
- Mimir 3.x defaults (ingest storage): verified by running monolithic with the classic path.
- Redaction regexes over-masking: tests check the masked shape, not just absence.
