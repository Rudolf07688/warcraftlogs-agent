---
name: gcp-firestore
description: >
  Interact with Google Cloud Firestore — a serverless, scalable NoSQL document database.
  Use when storing, querying, updating, or deleting documents and collections in Firestore
  from a Ruby server-side context. Covers client setup, CRUD operations, transactions,
  batched writes, BulkWriter, queries with cursors, aggregate queries, real-time listeners,
  data modeling, indexing, and performance best practices.
license: Proprietary
compatibility: Requires Ruby 3.x, the google-cloud-firestore gem (>= 3.0), and valid GCP credentials via GOOGLE_APPLICATION_CREDENTIALS or workload identity.
metadata:
  author: internal
  version: "1.0"
  sources: |
    https://firebase.google.com/docs/firestore
    https://docs.cloud.google.com/ruby/docs/reference/google-cloud-firestore/latest
    https://firebase.google.com/docs/firestore/best-practices
allowed-tools: Bash(bundle:*) Bash(gem:*) Read Write
---

# GCP Firestore Skill

Server-side integration with Google Cloud Firestore using the official Ruby client library (`google-cloud-firestore`). This skill covers everything from initial setup through production-grade data modeling, querying, and operational best practices.

---

## When to use Firestore

**Use Firestore when you need:**

- A managed, serverless NoSQL document store with automatic scaling and multi-region replication.
- Hierarchical data (collections → documents → subcollections) with flexible schema.
- Strong consistency on single-document reads and ACID transactions.
- Real-time listeners for live data sync.

**Avoid Firestore when you need:**

- Complex SQL joins or large analytical scan workloads (prefer BigQuery or Cloud SQL).
- Sub-millisecond latency at extreme write throughput per single document (prefer Bigtable).

---

## Setup

### Install the gem

```bash
gem install google-cloud-firestore
# or in Gemfile:
# gem "google-cloud-firestore", "~> 3.0"
```

### Authentication

Prefer **workload identity** (on GKE/Cloud Run) or **Application Default Credentials** for production. Use a service account JSON key only for local development — never commit it.

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

Required IAM role: `roles/datastore.user` (or `roles/datastore.owner` for admin operations).

### Client initialization

```ruby
require "google/cloud/firestore"

# Picks up project_id from GOOGLE_CLOUD_PROJECT or GCE metadata automatically.
# Pass project_id explicitly when running outside GCP.
firestore = Google::Cloud::Firestore.new(
  project_id: ENV.fetch("GCP_PROJECT_ID")
)
```

> **Best practice:** Instantiate the client once per process and reuse it. The client is thread-safe and manages connection pooling internally.

---

## Data Modeling

Model around **access paths and query patterns**, not relational normalization.

### Structure rules

| Rule | Rationale |
|------|-----------|
| Collections for entity types, documents for records | Clean hierarchy; enables collection-group queries |
| Subcollections for high-cardinality children | Avoids document size limit (1 MB per doc) |
| Denormalize read-heavy fields across documents | Eliminates fan-out reads; mirrors how Firestore is billed |
| Avoid sequential/lexicographic IDs (`user1`, timestamps) | Causes write hotspots; use UUID or auto-IDs |
| Keep document IDs free of `.`, `..`, `/` | Prevents path ambiguity and SDK escaping bugs |

### Example schema

```
users/{user_id}                              <- profile, preferences (small, < 50 KB)
users/{user_id}/sessions/{session_id}        <- session metadata
projects/{project_id}                        <- main project entity
projects/{project_id}/members/{member_id}    <- membership and roles
```

### Denormalization pattern

```ruby
# When a user's display_name changes, update denormalized copies atomically.
firestore.transaction do |tx|
  user_ref = firestore.doc "users/#{user_id}"
  tx.update user_ref, display_name: new_name

  affected_projects.each do |project_id|
    member_ref = firestore.doc "projects/#{project_id}/members/#{user_id}"
    tx.update member_ref, display_name: new_name
  end
end
```

---

## Core CRUD Operations

### Create

```ruby
users = firestore.col "users"

# Auto-generated ID (preferred; avoids sequential hotspots)
ref = users.add(
  name:       "Alice",
  email:      "alice@example.com",
  active:     true,
  created_at: Time.now
)
puts ref.document_id

# Explicit UUID
user_ref = users.doc(SecureRandom.uuid)
user_ref.set(
  name:       "Bob",
  email:      "bob@example.com",
  active:     true,
  created_at: Time.now
)
```

### Read

```ruby
snapshot = firestore.doc("users/#{user_id}").get

raise "Not found" unless snapshot.exists?
data = snapshot.data  # => Hash with symbolized keys
```

### Update

```ruby
user_ref = firestore.doc "users/#{user_id}"

# Merge: only update specified fields, preserving others
user_ref.update({ last_login_at: Time.now })

# Atomic transforms — avoid read-modify-write race conditions
user_ref.update(
  login_count: firestore.field_increment(1),
  tags:        firestore.array_union("pro"),
  old_roles:   firestore.array_delete("beta")
)
```

> Use `set(..., merge: true)` for upsert semantics when the document may not exist yet.

### Delete

```ruby
# Delete a document
firestore.doc("users/#{user_id}").delete

# Delete a specific field
user_ref.update({ temp_token: firestore.field_delete })
```

> For deleting large collections, use `BulkWriter` — never loop naive `delete` calls at scale.

---

## Queries

### Basic filter and sort

```ruby
active_users = firestore.col("users")
  .where("active", "==", true)
  .where("created_at", ">=", 30.days.ago)
  .order("created_at", :desc)
  .limit(50)

active_users.get do |doc|
  puts "#{doc.document_id}: #{doc[:name]}"
end
```

### Compound OR filters

```ruby
filter = Google::Cloud::Firestore::Filter.new("status", "==", "active")
            .or("status", "==", "pending")

firestore.col("orders").where(filter).get do |doc|
  puts doc.data
end
```

### Cursor-based pagination

```ruby
query = firestore.col("users").order("created_at", :desc).limit(20)

# Page 1
page1 = query.get.to_a
last  = page1.last

# Page 2
page2 = query.start_after(last).get.to_a
```

> Never use offsets — they scan and bill skipped documents. Always paginate with cursors.

### Aggregate queries

```ruby
# Count
count_result = firestore.col("users")
  .where("active", "==", true)
  .count.get
puts count_result.first.data[:count]

# Sum and average
firestore.col("orders").aggregate_query do |aq|
  aq.add_count
  aq.add_sum "total_amount"
  aq.add_avg "total_amount"
end.get
```

### Collection group queries

```ruby
# Query across ALL subcollections named "sessions" in the database
firestore.collection_group("sessions")
  .where("duration_seconds", ">", 3600)
  .get do |doc|
    puts doc.ref.path
  end
```

> Collection group queries require a composite index. Firestore error messages include a direct console URL to create it.

---

## Transactions

```ruby
firestore.transaction do |tx|
  user_ref  = firestore.doc "users/#{user_id}"
  stats_ref = firestore.doc "stats/global"

  user  = tx.get user_ref
  raise "Inactive user" unless user[:active]

  tx.update user_ref,  last_login_at: Time.now
  tx.update stats_ref, total_logins: firestore.field_increment(1)
end
```

**Guidelines:**

- Keep document count low — contention scales with number of documents touched.
- Avoid network I/O or long-running logic inside the transaction block.
- Transactions retry automatically on contention — ensure the block is idempotent.
- For large fan-out updates (many documents), prefer `BulkWriter` over a single transaction.

---

## Batched Writes & BulkWriter

### Atomic batch (up to 500 ops)

```ruby
batch = firestore.batch

ids_to_deactivate.each do |id|
  batch.update firestore.doc("users/#{id}"), active: false
end

batch.commit
```

### BulkWriter (large-scale writes with automatic rate limiting)

```ruby
bulk_writer = firestore.bulk_writer

records.each do |record|
  ref = firestore.doc "events/#{record[:id]}"
  bulk_writer.set ref, record
end

bulk_writer.flush  # waits for all pending writes
bulk_writer.close
```

> `BulkWriter` respects Firestore's write ramp-up limits and retries with exponential backoff. Use it for migrations and bulk ingestion.

---

## Real-Time Listeners

```ruby
# Document listener
listener = firestore.doc("users/#{user_id}").listen do |snapshot|
  puts "Updated: #{snapshot.data}"
end

# Query listener
query_listener = firestore.col("orders")
  .where("status", "==", "pending")
  .listen do |snapshot|
    snapshot.changes.each do |change|
      case change.type
      when :added    then puts "New: #{change.doc.document_id}"
      when :modified then puts "Changed: #{change.doc.document_id}"
      when :removed  then puts "Removed: #{change.doc.document_id}"
      end
    end
  end

listener.stop
query_listener.stop
```

---

## Indexing

Firestore auto-indexes most single fields. Composite indexes must be created manually for multi-field queries.

| Index type | When needed |
|------------|-------------|
| Composite index | Filter or sort on 2+ different fields |
| Array index (auto) | Queries using `array_contains` |
| Descending index | `order(:desc)` on a field; disable if unused to reduce write cost |

**Best practices:**

- Run queries in development — error messages include a console URL to create missing indexes.
- Exempt fields you never query (e.g. large blobs) to reduce write latency and storage cost.
- Keep array fields small — each array element multiplies index write cost (fan-out).

---

## Performance & Traffic Ramp-Up

### 500/50/5 ramp-up rule

When writing to a new collection for the first time:

1. Start at ~**500 operations/second**.
2. Increase by at most **50%** every **5 minutes**.
3. Distribute operations **uniformly across the key space** (use UUID/auto-IDs).

Violating this causes hotspot errors and elevated latency.

### Hotspot avoidance checklist

- [ ] Document IDs are random (auto-ID or `SecureRandom.uuid`), not sequential or timestamp-based.
- [ ] High write-rate counters use `field_increment`, not read-modify-write.
- [ ] Large fan-out changes use `BulkWriter`, not a single transaction.
- [ ] Queries are not repeatedly fetching non-existent documents at high rates.

---

## Security

- Use **IAM roles** for server-side access (`roles/datastore.user` minimum).
- Use **Firestore Security Rules** for client SDK access (mobile/web).
- **Never store** sensitive data in document IDs, collection names, or field names — these appear in logs.
- Prefer **workload identity** over JSON service account keys in production.
- Grant **least-privilege** IAM: read-only services get `roles/datastore.viewer`.

---

## Location Selection

| Option | Write Latency | Durability | Cost |
|--------|--------------|-----------|------|
| Regional | Lowest | Single region | Lower |
| Multi-region (nam5, eur3) | Slightly higher | Multi-region failover | Higher |

Choose a location **co-located with your Cloud Run or GKE cluster**.

---

## Migrations (Zero-Downtime Pattern)

1. **Dual-write:** Write new data to both old and new collection/schema.
2. **Backfill:** Use `BulkWriter` to migrate existing documents in batches with random ID distribution.
3. **Read cutover:** Switch reads to prefer new schema (new → fallback to old).
4. **Decommission:** Once validated, stop writing to old collection and delete it.

---

## Key Limits

| Limit | Value |
|-------|-------|
| Document size | 1 MB |
| Sustained writes per document | 1 write/sec |
| Max ops per transaction or batch | 500 |
| Max fields in a composite index | 100 |
| Free tier reads | 50,000/day |
| Free tier writes | 20,000/day |

---

## Common Pitfalls

| Pitfall | Fix |
|---------|-----|
| Sequential document IDs | Use `add` (auto-ID) or `SecureRandom.uuid` |
| Growing arrays in documents | Move items to a subcollection |
| Offset-based pagination | Use `start_after` cursor pagination |
| Naive loop deletes at scale | Use `BulkWriter` |
| Read-modify-write for counters | Use `field_increment` |
| Long-running I/O inside transactions | Move I/O outside the transaction block |
| Missing composite indexes | Follow the console URL in Firestore error messages |
