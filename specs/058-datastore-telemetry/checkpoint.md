# Checkpoint: 058 (before implementation)

- Decisions: board scope:058:* #30–#38 (commenter, docker-access, cadvisor, metrics-path, query-text,
  pg-logs, monitor-role, alerts); backlog:sqlalchemy-double-tracer #31.
- Files: plan.md "Source Code" list (brief footprint).
- Facts that shape the code: take the LAST traceparent (research R3); cAdvisor needs containerd.sock
  (R1); jsonlog impossible without logging_collector (R4); import create_async_engine after instrument().
- Implementation starts at T002 (compose), then T004 migration, T006 test skeleton, then US1.
- Test stack: COMPOSE_PROJECT=wcl-obs-ansel, ports 25xxx; pg.py ansel is up (15440) for pytest --pg.
