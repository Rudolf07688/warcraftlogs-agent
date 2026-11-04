#!/usr/bin/env bash
# Re-read the team board into Loki (feature 055, sc-407). Run it after Loki lost its data
# (volume removed or rebuilt). Alloy keeps how far it has read each board file on its data
# volume; this stops Alloy, deletes the board tail's positions and starts Alloy again, which
# then reads every board file from the start. Entries keep their own timestamps and text, so
# entries Loki still holds are not duplicated. Loki refuses entries older than its
# reject_old_samples window (7 days by default): older sprints are in meta/sprints/*/board.jsonl.
#
#   observability/board-backfill.sh                       (the compose project of this checkout)
#   COMPOSE_PROJECT=wcl-obs-test observability/board-backfill.sh
#
# In a worktree, export TEAM_BOARD_DIR as for `docker compose up` (see docker-compose.yml).
set -euo pipefail
cd "$(dirname "$0")/.."

project=()
[[ -n "${COMPOSE_PROJECT:-}" ]] && project=(-p "$COMPOSE_PROJECT")
dc() { docker compose --progress quiet "${project[@]}" "$@"; }

dc stop alloy
dc run --rm --no-deps -T --entrypoint rm alloy -f /var/lib/alloy/data/loki.source.file.board/positions.yml
dc start alloy
echo "board-backfill: Alloy restarted; it re-reads every board file now"
