---
id: board-hook-reader-and-filter
anchors: [sym:.claude/team/board.py::cmd_hook, sym:.claude/team/board.py::reader_from_hook, sym:.claude/team/board.py::addressees]
by: dev-3 Nils
verified: 6ee1c04 2026-11-07
---
The hook names an unnamed sub-agent's reader once, from the --as of its first real
`board.py post/read` argv (shlex, heredocs and quoted text ignored) and only if the name is on
the meta/team roster; stored as cursors/reader--<agent id>, never re-bound. Dev seats get the
filtered feed (relevant()). The hook shows the oldest unread first and moves the cursor only
past what it showed. post --to refuses non-roster names. Test in a temp git repo with seat
files under <repo>/meta/team/.
