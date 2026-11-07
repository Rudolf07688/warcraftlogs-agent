---
id: shortcut-sync-iteration-sweep
anchors: [file:.claude/agents/shortcut-sync.md, file:.claude/skills/shortcut-sync/]
by: po Maren
source: meta/team/po.md L17; meta/sprints/2026-11-02/board.jsonl #77; meta/sprints/2026-11-05/board.jsonl #109
verified: d4ccc69 2026-11-07
---
shortcut-sync's tidy step assigns the active iteration to every Shortlist, In Progress or
Under Review story that lacks one. During a sprint that puts the sprint iteration on
unrelated Shortlist stories, such as next-sprint candidates. After each sync, check the
iteration and remove it from stories that aren't sprint work.
