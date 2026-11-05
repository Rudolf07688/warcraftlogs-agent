---
id: uploader-text-neutralise
anchors: [sym:wcl_agent/tools/report_tools.py::neutralise, sym:wcl_agent/tools/report_tools.py::_bounded, file:backend/app/kb/search.py]
by: dev-3 Nils
source: meta/team/dev-3.md L17; meta/sprints/2026-11-02/board.jsonl #53, #63
verified: b9cf9a3 2026-11-05
---
Uploader-controlled WCL text (player names, report titles, guilds) reaches the model only
through `report_tools.neutralise`, then a cap (`_bounded`/`_bounded_strings`,
`MAX_NAME_CHARS`). KB search uses the same neutraliser for its `<data>` blocks. Neutralise
after projecting down to the fields you return (QA PERF-001), and cap after neutralising,
because NFKC can lengthen text.
