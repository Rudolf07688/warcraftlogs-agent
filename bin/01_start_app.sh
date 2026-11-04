#!/bin/bash

BUILD_FLAG=${1:-""}


# ------------------ Start App ------------------ #
echo " -- Starting Application -- "

bash bin/00_init_migrate_db.sh
if [ $? != 0 ]; then
    echo "ERROR: Database initialization and migration failed"
    exit 1
fi

echo " -- DB Initialization and Migration Complete -- "

echo " -- Launching Application -- "
# service.version on the backend's telemetry (the image has no .git to read it from).
export WCL_GIT_SHA=$(git rev-parse --short HEAD)
docker compose up -d $BUILD_FLAG 2>&1
if [ $? != 0 ]; then
    echo "ERROR: Failed to launch application"
    exit 1
fi

docker compose ps

echo " -- Application Launched -- "

cleanup() {
    trap - INT TERM EXIT
    echo " -- Stopping Application -- "
    kill $PID 2>/dev/null
    docker compose down
    exit 0
}
trap cleanup INT TERM EXIT

docker compose logs -f & PID=$!
echo " -- Logs Streaming -- "
wait $PID
