---
id: qa-reports-gitignored
anchors: [file:.gitignore]
by: po Maren
source: meta/team/po.md L14
verified: d4ccc69 2026-11-07
---
`qa-reports/` is gitignored, so QA reports exist only in the worktree where they were
written, usually the sprint worktree: P7 reviews in `qa-reports/<date>/`, the end sweep in
`qa-reports/<date>-sweep/`. They never reach main. Cite them by worktree path, and copy
anything that must last into a committed sprint file (for example `qa-triage.md`).
