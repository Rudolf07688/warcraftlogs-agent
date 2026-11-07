#!/bin/bash

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
# One idempotent command: upgrade to 0002, create the founder only if none exists, upgrade to
# head. It never re-bootstraps an existing database.
out=$(uv run python -m backend.cli.init_db 2>&1)
rc=$?
echo "$out"
if [ $rc != 0 ]; then
    rev=$(echo "$out" | sed -n "s/.*Can't locate revision identified by '\([^']*\)'.*/\1/p" | head -1)
    if [ -n "$rev" ]; then
        echo ""
        echo "ERROR: the database is at migration '$rev', which this checkout doesn't have."
        echo "  It was migrated from a newer branch (usually a sprint branch that isn't merged yet)."
        echo "  Branches that have it:"
        git branch --format='%(refname:short)' --contains "$(git log --all --format=%H -1 -- "backend/migrations/versions/${rev}.py")" 2>/dev/null | grep -E '^(main|sprint-)' | sed 's/^/    /'
        echo "  Fix: check out one of them (git checkout --detach <branch>), or restore a backup:"
        ls -t "$(git rev-parse --git-common-dir)"/db-backups/*.dump 2>/dev/null | head -3 | sed 's/^/    /'
    fi
    exit 1
fi

echo " -- Migration Complete -- "
