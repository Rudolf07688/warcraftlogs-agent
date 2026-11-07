---
id: compose-env-file-vs-service-env-file
anchors: [file:docker-compose.yml]
by: dev-1 Ansel
verified: 9ff8602 2026-11-07
---
docker compose --env-file F replaces the checkout's .env only for ${VAR} interpolation. The db
service's env_file (.env, required: false) and backend's (required) still read .env into the
container, and 'compose config' fails in a worktree without one. stack.py therefore refuses db,
backend and frontend in a checkout that has a .env; the observability services have no env_file.
