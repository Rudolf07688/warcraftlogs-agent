---
id: target-info-labels
anchors: [file:observability/mimir/rules/anonymous/cross.yaml, comp:mimir]
by: dev-2 Tomas
source: meta/team/dev-2.md L24
verified: b9cf9a3 2026-11-05
---
`target_info{job="wcl-agent/api"}` carries `service_version` (and `vcs_ref_head_revision`)
but no `service_name`. Derive the name from `job` with `label_replace(..., "service_name",
"$1", "job", "wcl-agent/(.+)")`. `service.version` is not a promoted label, so only
`target_info` knows which version is running.
