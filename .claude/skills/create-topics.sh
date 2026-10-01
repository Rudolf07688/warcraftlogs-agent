#!/usr/bin/env bash
# Create standard Kafka topics for local dev
# Usage: ./scripts/create-topics.sh [bootstrap-server]

BOOTSTRAP="${1:-localhost:9092}"

topics=(
  "orders.created:6:1"
  "orders.cancelled:6:1"
  "payments.processed:6:1"
  "users.registered:3:1"
  "orders.created.dlq:1:1"
  "orders.cancelled.dlq:1:1"
)

for topic_spec in "${topics[@]}"; do
  IFS=':' read -r topic partitions replication <<< "$topic_spec"
  kafka-topics.sh \
    --bootstrap-server "$BOOTSTRAP" \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions "$partitions" \
    --replication-factor "$replication"
  echo "Created: $topic (partitions=$partitions, replication=$replication)"
done

echo ""
echo "All topics:"
kafka-topics.sh --bootstrap-server "$BOOTSTRAP" --list
