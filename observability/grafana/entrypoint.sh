#!/bin/sh
# Grafana start-up for the observability profile (QA fix of 053, SEC-002): the built-in admin
# account's password is GRAFANA_ADMIN_PASSWORD, set again on every start, so an older
# grafana-data volume created with admin/admin is fixed too. Unset or empty: a random
# password nobody knows, i.e. no admin login; anonymous visitors are Viewers either way.
set -eu
if [ -z "${GF_SECURITY_ADMIN_PASSWORD:-}" ]; then
  GF_SECURITY_ADMIN_PASSWORD="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
  echo "grafana: GRAFANA_ADMIN_PASSWORD is not set; admin login disabled (anonymous Viewer only)"
fi
export GF_SECURITY_ADMIN_PASSWORD
# A new volume has no database yet: Grafana then creates the admin from the variable.
if [ -f "${GF_PATHS_DATA}/grafana.db" ]; then
  printf '%s\n' "$GF_SECURITY_ADMIN_PASSWORD" \
    | grafana cli --homepath "$GF_PATHS_HOME" --config "$GF_PATHS_CONFIG" \
        admin reset-admin-password --password-from-stdin >/dev/null
fi
exec /run.sh "$@"
