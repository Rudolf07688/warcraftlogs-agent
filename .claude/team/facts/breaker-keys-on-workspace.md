---
id: breaker-keys-on-workspace
anchors: [sym:backend/app/services/raw_fetch_reads.py::Breaker]
by: dev-2 Tomas
source: meta/team/dev-2.md L18; meta/sprints/2026-11-02/board.jsonl #52
verified: b9cf9a3 2026-11-05
---
The raw-store probe breaker keys its timeouts by workspace (tenant id). When one workspace
reaches `TIMEOUTS_TO_OPEN` (3) timeouts in `WINDOW_S` (60 s), only that workspace skips the store. The breaker opens
for everyone only when two or more workspaces time out and those timeouts are at least half
of the window's probes. Limits on a shared resource key on the workspace, never on turns or
users.
