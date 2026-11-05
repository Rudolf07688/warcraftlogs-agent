---
id: loki-rejects-old-entries
anchors: [comp:loki]
by: dev-1 Ansel
source: meta/team/dev-1.md; observability/README.md
verified: b9cf9a3 2026-11-05
---
Loki refuses an entry more than about an hour older than its stream's newest entry with a 400, a
permanent failure. Replaying or seeding old log data into an existing stream fails this way; use
a new stream label or fresh timestamps. Details: observability/README.md.
