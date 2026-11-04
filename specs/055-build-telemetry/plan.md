# Implementation Plan: Build telemetry (055)

**Branch**: `055-build-telemetry` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

## Summary

Four stories on the observability stack of 053/054, all config plus two small Python tools:
a Mimir ruler with version-controlled rules (foundation), the team board tailed into Loki
through Alloy's redaction chain with a traceparent per entry (407), spanmetrics and
servicegraph connectors plus RED aliases (409), the D1/D2 dashboards on `cc:*` aliases with
seat cost from teamstats (408), and a pricing table generated into cost recording rules (410).

## Technical Context

**Language/Version**: Python 3.14 (stdlib only for `.claude/team/*.py` and the generator), Alloy config syntax, PromQL, Grafana dashboard JSON
**Primary Dependencies**: pinned images: grafana/alloy v1.21.3, grafana/mimir 3.2.4, grafana/loki 3.7.9, grafana/tempo 2.10.10 (compose); mimirtool via a pinned docker image for rule lint
**Storage**: Mimir local ruler storage `/etc/mimir/rules/anonymous/*.yaml` (mounted read-only); board JSONL files
**Testing**: pytest (`backend/tests/test_team_*.py`: board.py, teamstats.py, pricing drift); stack scripts under `observability/test/` (compose project `wcl-obs-ansel`, 25xxx ports)
**Target Platform**: local docker compose, observability profile
**Project Type**: infrastructure config + agent tooling
**Constraints**: footprint per board `owner:stream-a`; Faro section of config.alloy is Tomas's; runtime.yaml is Nils's
**Scale/Scope**: < 50k active series (spec §9.3): spanmetrics dimensions are bounded enums only

## Constitution Check

- I Reuse: the board tail reuses the existing redaction/classify chain (no second redaction path); seat cost reuses teamstats' weights and usage.txt parser; dashboards reuse D1's uid. PASS
- II Small steps: one commit per story after the ruler foundation, each with its proof script. PASS
- III Simplicity: price constants as generated recording rules instead of an exporter container; no new services. PASS
- IV Typed: n/a for config; Python tools keep plain dict entries as today (JSONL contract unchanged plus one optional field). PASS
- V Async: no backend code. PASS
- VI GitNexus: impact on `cmd_post`, `parse_usage`, `build_payload`, `collect` before edits. PASS
- VII shadcn: no UI. PASS
- VIII Shortcut: stories to In Progress / Under Review. PASS

## Project Structure

```text
.claude/team/board.py            traceparent per entry (407)
.claude/team/teamstats.py        team.seat.cost_usd per sprint (408)
bin/claude-otel                  comment fix (407)
docker-compose.yml               alloy: board dir mount; mimir: rules mount
observability/alloy/config.alloy board tail section, classify carve-out, spanmetrics/servicegraph section
observability/mimir/mimir.yaml   ruler: local storage, poll 1m
observability/mimir/rules/anonymous/{build,red,cost}.yaml
observability/pricing/{pricing.yaml,generate.py}
observability/grafana/dashboards/build/{claude-code-overview.json,agent-team.json,agent-team-improvement.json (link only)}
observability/board-backfill.sh  reset the board tail position after Loki data loss
observability/test/{board.sh,board_check.py,red.sh,rules.sh,rules_check.py,dashboards.sh}, lib.sh (TEAM_BOARD_DIR, rules helpers)
backend/tests/test_team_board.py, test_team_teamstats.py, test_team_pricing.py
```

## Phases

0. Foundation: ruler enabled, empty-but-valid rule files load (`rules.sh` lists groups).
1. 407 board tail + backfill + redaction proof (`board.sh`).
2. 409 connectors + `red.yaml` (`red.sh`).
3. 408 `build.yaml`, D1/D2, teamstats seat cost (`dashboards.sh`, unit tests).
4. 410 pricing + `cost.yaml` (`rules.sh` arithmetic for Claude and Gemini).

## Complexity Tracking

None.
