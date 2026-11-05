# Quickstart: 058

```bash
# Stack proofs (project wcl-obs-ansel, 25xxx ports; KEEP=1 leaves it up)
COMPOSE_PROJECT=wcl-obs-ansel observability/test/datastores.sh   # 417, 418, 419, 420
COMPOSE_PROJECT=wcl-obs-ansel observability/test/alerts.sh       # 424
# Backend
python3 .claude/team/check.py run --as ansel
python3 .claude/team/check.py run --pg ansel                     # 0022 up/down
```

Owner's stack: set `PG_MONITOR_PASSWORD` in `.env`, run migrations, recreate `db` and `alloy`
(`docker compose up -d db alloy docker-proxy`), and with the profile `cadvisor`.
