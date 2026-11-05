---
id: rule-ratio-guards
anchors: [file:observability/mimir/rules/anonymous/, comp:mimir]
by: dev-2 Tomas
source: meta/team/dev-2.md L24
verified: b9cf9a3 2026-11-05
---
In recording rules, divide by `(denominator > 0)` and clamp `histogram_quantile(...)` with
`>= 0`. Otherwise an idle window records NaN or Inf, and a single NaN poisons every
`avg_over_time` over that range. `cross.yaml` and `runtime.yaml` (sc-508) guard every division,
and a test enforces it for `runtime.yaml`; its `histogram_quantile` rules are not clamped yet.
