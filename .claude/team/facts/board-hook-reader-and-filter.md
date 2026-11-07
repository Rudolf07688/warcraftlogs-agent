---
id: board-hook-reader-and-filter
anchors: [sym:.claude/team/board.py::cmd_hook, sym:.claude/team/board.py::reader_from_hook]
by: dev-3 Nils
verified: c614ae5 2026-11-07
---
The hook names its reader from the last Bash command with 'board.py ... --as <lower-case name>'
(stored as a per-agent alias), else from the agent id. Only readers whose meta/team/dev-<n>.md
seat file names them get the filtered feed (relevant()); everyone else, unmapped sub-agents
included, gets everything. The cursor always advances past filtered entries. Test the hook in a
temp git repo with seat files under <repo>/meta/team/, never on the live board.
