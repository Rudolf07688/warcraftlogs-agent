#!/usr/bin/env bash
# Register a Debezium PostgreSQL CDC connector
# Usage: ./scripts/register-cdc-connector.sh [connect-url]

CONNECT_URL="${1:-http://localhost:8083}"

curl -X POST "$CONNECT_URL/connectors" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "pg-cdc-connector",
    "config": {
      "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
      "database.hostname": "postgres",
      "database.port": "5432",
      "database.user": "debezium",
      "database.password": "dbz_password",
      "database.dbname": "app_db",
      "topic.prefix": "cdc",
      "schema.include.list": "public",
      "table.include.list": "public.orders,public.customers",
      "publication.name": "dbz_publication",
      "slot.name": "debezium_slot",
      "plugin.name": "pgoutput",
      "snapshot.mode": "initial",
      "tombstones.on.delete": "true",
      "heartbeat.interval.ms": "10000",
      "key.converter": "org.apache.kafka.connect.json.JsonConverter",
      "value.converter": "org.apache.kafka.connect.json.JsonConverter",
      "key.converter.schemas.enable": "false",
      "value.converter.schemas.enable": "false"
    }
  }' | jq .

echo ""
echo "Connector status:"
curl -s "$CONNECT_URL/connectors/pg-cdc-connector/status" | jq .
