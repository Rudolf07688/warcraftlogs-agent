---
id: compose-env-file-vs-service-env-file
anchors: [file:docker-compose.yml]
by: dev-1 Ansel
verified: 9fc3890 2026-11-07
---
docker compose --env-file F replaces the checkout's .env only for ${VAR} interpolation. Compose
still opens every service's env_file while building the model, selected or not (db: .env,
required: false; backend: .env), and 'compose config' fails in a worktree without one. So
stack.py refuses up and down in any checkout with a .env; run it from a worktree without one
(env files live in the git common dir, so any worktree can down a stack).
