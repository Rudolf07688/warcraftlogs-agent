---
id: stack-env-same-bash-call
anchors: [file:observability/test/, comp:compose]
by: dev-1 Ansel
source: meta/team/dev-1.md L19
verified: 20d4197 2026-11-07
---
Each Bash tool call starts a fresh shell, so the env you exported in one call is gone in the
next. A stack script then silently falls back to `lib.sh` defaults: project `wcl-obs-test`
on the 24xxx ports, which belong to team-lead. Keep your stack env (`COMPOSE_PROJECT=wcl-obs-<name>` and your
port block) in a scratch file and source it in the same call as the script.
