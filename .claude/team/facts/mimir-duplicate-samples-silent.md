---
id: mimir-duplicate-samples-silent
anchors: [comp:mimir, comp:alloy]
by: dev-1 Ansel
source: meta/team/dev-1.md; board sprint-2026-11-05 live pass
verified: b9cf9a3 2026-11-05
---
Mimir counts points with the same labels and timestamp in one request as
sample_duplicate_timestamp, answers 200 and logs nothing. The symptom is an undercount; the
usual cause is an Alloy transform that drops an attribute and collapses OTLP points. Check
cortex_discarded_samples_total by reason after any Alloy attribute change. Details:
observability/README.md.
