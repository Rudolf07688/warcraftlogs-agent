#!/bin/bash

# ------------------ Functions ------------------ #
alb_upgrade_head() {
    echo " -- Alembic upgrade head --"
    uv run alembic -c backend/alembic.ini upgrade head               # tenant_id backfill + RLS
}


alb_bootstrap() {
    echo " | Attemping fresh bootstrap"
    uv run alembic -c backend/alembic.ini upgrade 0002_auth_tenancy   # auth/tenant tables
    uv run python -m backend.cli.bootstrap_admin                      # create the founder
}

# ------------------ Start ------------------ #
echo " -- Initializing and Migrating Database -- "

source .env

# ------------------ UV ------------------ #
uv sync --all-extras
if [ $? != 0 ]; then
    echo "uv sync failed; creating new venv"
    uv venv .venv
fi

# -- Fresh UV env -- #
source .venv/bin/activate
uv sync --all-extras
if [ $? != 0 ]; then
    echo "ERROR: UV environment setup failed"
    exit 1
fi

# ------------------ Start Database ------------------ #
docker compose up -d db
if [ $? != 0 ]; then
    echo "ERROR: Failed to start database"
    exit 1
fi

# ------------------ Alembic Migration ------------------ #
alb_upgrade_head
if [ $? != 0 ]; then
    echo "-! Upgrade failed !-"
    alb_bootstrap || exit $?
    alb_upgrade_head || exit $?
fi

echo " -- Migration Complete -- "
