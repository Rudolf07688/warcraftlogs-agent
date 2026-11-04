# Tasks: 055 build telemetry

## Phase 0: Foundation (contract:recording-rules)
- [ ] T001 mimir.yaml ruler local storage + docker-compose mimir rules mount; rules/anonymous/ placeholder files
- [ ] T002 lib.sh: TEAM_BOARD_DIR temp default, mimir rule helpers; rules.sh lists loaded groups
- [ ] T003 Verify on wcl-obs-ansel, post final path on contract:recording-rules

## Phase 1: sc-407 board into Loki
- [ ] T010 board.py: store TRACEPARENT (validated) per entry; fmt unchanged for old entries
- [ ] T011 backend/tests/test_team_board.py: stored, absent, invalid, old entries read/current/wait
- [ ] T012 config.alloy board section + classify carve-out; compose alloy board mount
- [ ] T013 observability/board-backfill.sh
- [ ] T014 observability/test/board.sh + board_check.py (labels, trace id, secret masked, backfill)
- [ ] T015 bin/claude-otel comment fix; README section

## Phase 2: sc-409 RED
- [ ] T020 config.alloy spanmetrics + servicegraph section
- [ ] T021 rules/anonymous/red.yaml
- [ ] T022 observability/test/red.sh (+ check): series, exemplars, no id labels, aliases, exclusions

## Phase 3: sc-408 D1/D2
- [ ] T030 rules/anonymous/build.yaml (cc:*)
- [ ] T031 teamstats.py team.seat.cost_usd + tests
- [ ] T032 D1 extended on aliases; D2 agent-team.json; D13 link
- [ ] T033 observability/test/dashboards.sh (provision + every metric expr uses an alias; cost titles)

## Phase 4: sc-410 pricing
- [ ] T040 pricing.yaml + generate.py -> rules/anonymous/cost.yaml
- [ ] T041 backend/tests/test_team_pricing.py (drift, per-token math)
- [ ] T042 rules.sh arithmetic: Claude + Gemini synthetic native histograms

## Close
- [ ] T050 README, live-check questions, check.py receipt, hand-off
