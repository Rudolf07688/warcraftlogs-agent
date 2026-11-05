---
id: promql-timestamp-bare-selector
anchors: [file:observability/mimir/rules/anonymous/cross.yaml, comp:mimir]
by: dev-2 Tomas
source: meta/team/dev-2.md L21
verified: 32010a6 2026-11-05
---
PromQL `timestamp()` returns a sample's own time only for a bare selector. On any computed
vector it returns the evaluation time. To prefer one class of series, join two
`timestamp(selector)` with `or on (label)`, then take `topk`, as `cross:running_version:info`
does.
