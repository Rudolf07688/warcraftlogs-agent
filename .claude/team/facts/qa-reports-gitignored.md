---
id: qa-reports-gitignored
anchors: [file:.gitignore, comp:team]
by: po Maren
source: meta/team/po.md L14
verified: b9cf9a3 2026-11-05
---
`qa-reports/` is gitignored, so QA reports exist only in the worktree where they were
written, usually the sprint worktree: P7 reviews in `qa-reports/<date>/`, the end sweep in
`qa-reports/<date>-sweep/`. They never reach main. Cite them by worktree path, and copy
anything that must last into a committed sprint file (for example `qa-triage.md`).
