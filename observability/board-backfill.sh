#!/usr/bin/env bash
# Re-read the team board into Loki (feature 055, sc-407). Run it after Loki lost its data
# (volume removed or rebuilt). Alloy keeps how far it has read each board file on its data
# volume; this stops Alloy, deletes the board tail's positions and starts Alloy again, which
# then reads every board file from the start. Entries keep their own timestamps and text, so
# entries Loki still holds are not duplicated. Only the last 6 days come back: Alloy's
# log_window drops older records (Loki refuses anything past its 7-day reject_old_samples
# window). Accepted on purpose (feature 059, board scope:059:board-window): that limit is
# per tenant, so it can't widen for the board alone, and widening it for every stream would
# admit week-old content records. Older sprints are in meta/sprints/*/board.jsonl.
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
