---
id: mimir-otlp-metric-names
anchors: [comp:mimir, file:observability/mimir/]
by: dev-1 Ansel, dev-3 Nils
source: meta/team/dev-1.md, dev-3.md; observability/README.md Recording rules
verified: b9cf9a3 2026-11-05
---
Over OTLP, Mimir keeps the OTel metric name with dots turned into underscores and adds no unit
or _total suffix (app.llm.finish_reasons -> app_llm_finish_reasons); histograms are native, with
no _bucket/_count series unless a rule makes them. Scraped exporters keep their Prometheus
names. Details: observability/README.md, Recording rules.
