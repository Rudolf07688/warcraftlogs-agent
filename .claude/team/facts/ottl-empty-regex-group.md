---
id: ottl-empty-regex-group
anchors: [file:observability/alloy/config.alloy, comp:alloy]
by: dev-1 Ansel
source: meta/team/dev-1.md L19
verified: b9cf9a3 2026-11-05
---
On Alloy's `loki.process` -> `otelcol.receiver.loki` path, a regex group that matched nothing
arrives as an attribute holding an empty string, not as a missing attribute. Delete it
(`delete_key(...) where attributes["x"] == ""`, as the postgres transform does) and test
values with `IsMatch`, not `!= nil`.
