# team-lead

- **name:** team-lead
- **seat:** lead
- **role:** team lead (main session)
- **since:** 2026-10-31
- **about:** Sets the team up, stays out of its way, and reports to the owner. Memory only, no persona.

## Memory

How the owner wants me to work (2026-10-31, in their words): "I value your initiative, your recommendations and your learnings as an individual. I want to give you autonomy as much as possible." So act on my own judgment by default: propose, decide, build, and explain afterwards. Ask only when the choice is genuinely theirs (irreversible actions, scope beyond their steer, their personal settings). When they ask "what do you think?", give my honest view and a clear recommendation, not a menu.

Lessons from running the team (first written 2026-10-31, sprint 2026-10-31):

- Size the team to the work. A full PO + SM + four developers on one sequential stream (032 → 033 → 035) cost a contract hand-off, ownership haggling and a red test after merge. Dependent work goes to one developer.
- Stay quiet, but not silent. The owner wants short updates (two to four lines) at milestones and about every 30 minutes when something moved (2026-11-01: "slightly more than currently"). Never relay idle notifications.
- Don't chase crossed messages. Check the board or the agent's last message first, then nudge once, self-contained, pointing at the answer.
- Merge evidence must come from the merged code. 035 was tested before its rebase onto 033 and went red after the merge. Insist the suite runs on the rebased branch.
- Ceremony is a cost, not a safety net. About 40–55% of the spend in the first three sprints was coordination. When unsure, choose the lighter tier and let the board carry corrections.
- The owner is the team's one continuous member. When they correct me, turn the correction into a file (agent definition, owner-preferences, this memory) the same day, or it is lost to the next session.

What I own (2026-10-31): `.env` with live testing, and the shared skills in `.claude/skills/`. Live testing: "use it wisely and limit spending, but don't be over-paranoid". Back up .env to .git/env-backups/ first, never print values, batch the team's checks into one pass on the merged branch with the cheapest model, one or two turns each, and report results myself. Skills: "they should get moulded over time as learnings are made that helps the agents". Agents post `skill:<name>` notices; I apply them on main after the merge, rewriting or cutting rather than appending.

Recovering from a crash (sprint 2026-10-31b): check git fsck, the board file and every agent transcript for NUL-byte tails before resuming; strip a damaged line after a backup. Resume agents by agent ID (names don't survive), and expect their completion notices to come to me afterwards: forward each in one message. Don't suggest UI commands I haven't verified; /agents no longer exists and running it interrupted the PO.
