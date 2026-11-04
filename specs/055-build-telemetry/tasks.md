# Tasks: 055 build telemetry

## Phase 0: Foundation (contract:recording-rules)
- [X] T001 mimir.yaml ruler local storage + docker-compose mimir rules mount; rules/anonymous/ placeholder files
- [X] T002 lib.sh: TEAM_BOARD_DIR temp default, mimir rule helpers; rules.sh lists loaded groups
- [X] T003 Verify on wcl-obs-ansel, post final path on contract:recording-rules

## Phase 1: sc-407 board into Loki
- [X] T010 board.py: store TRACEPARENT (validated) per entry; fmt unchanged for old entries
- [X] T011 backend/tests/test_team_board.py: stored, absent, invalid, old entries read/current/wait
- [X] T012 config.alloy board section + classify carve-out; compose alloy board mount
- [X] T013 observability/board-backfill.sh
- [X] T014 observability/test/board.sh + board_check.py (labels, trace id, secret masked, backfill)
- [X] T015 bin/claude-otel comment fix; README section

## Phase 2: sc-409 RED
- [X] T020 config.alloy spanmetrics + servicegraph section
- [X] T021 rules/anonymous/red.yaml
- [X] T022 observability/test/red.sh (+ check): series, exemplars, no id labels, aliases, exclusions

## Phase 3: sc-408 D1/D2
- [X] T030 rules/anonymous/build.yaml (cc:*)
- [X] T031 teamstats.py team.seat.cost_usd + tests
- [X] T032 D1 extended on aliases; D2 agent-team.json; D13 link
- [X] T033 observability/test/dashboards.sh (provision + every metric expr uses an alias; cost titles)

## Phase 4: sc-410 pricing
- [X] T040 pricing.yaml + generate.py -> rules/anonymous/cost.yaml
- [X] T041 backend/tests/test_team_pricing.py (drift, per-token math)
- [X] T042 rules.sh arithmetic: Claude + Gemini synthetic native histograms

## Close
- [X] T050 README, live-check questions, check.py receipt, hand-off
- [X] T034 D1 cost and tokens over time panels (owner, steer:overview-panels)
