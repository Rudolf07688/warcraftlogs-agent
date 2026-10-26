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
docker compose up -d $BUILD_FLAG 2>&1
if [ $? != 0 ]; then
    echo "ERROR: Failed to launch application"
    exit 1
fi

docker compose ps

echo " -- Application Launched -- "

docker compose logs -f & PID=$!; 
echo " -- Logs Streaming -- "
