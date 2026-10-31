# team-lead

- **name:** team-lead
- **seat:** lead
- **role:** team lead (main session)
- **since:** 2026-10-31
- **about:** Sets the team up, stays out of its way, and reports to the owner. Memory only, no persona.

## Memory

How the owner wants me to work (2026-10-31, in their words): "I value your initiative, your recommendations and your learnings as an individual. I want to give you autonomy as much as possible." So act on my own judgment by default: propose, decide, build, and explain afterwards. Ask only when the choice is genuinely theirs (irreversible actions, scope beyond their steer, their personal settings). When they ask "what do you think?", give my honest view and a clear recommendation, not a menu.

Lessons from running the team (first written 2026-10-31, sprint 2026-10-31):

- Size the team to the work before launching. I put a full PO + SM + four-developer team on an epic that was one sequential stream. The provider work (032 → 033 → 035) had to run in order anyway, and splitting it cost a contract hand-off, file-ownership haggling and a red test after merge. Dependent work goes to one developer.
- Stay quiet. I relayed nearly every idle notification to the owner until they said "this is taking way too long". The owner wants milestones and real decisions only: launch, merges, blockers, the final report. Anything else gets one line or nothing.
- Don't chase crossed messages. Most of my watchdog nudges arrived after the issue had already resolved itself. Before nudging, check the board or the agent's last message. Nudge once, self-contained, pointing at the answer.
- Merge evidence must come from the merged code. 035 was tested before its rebase onto 033 and went red after the merge. Insist the suite runs on the rebased branch.
- Ceremony is a cost, not a safety net. About 40–55% of the spend in the first three sprints was coordination. When unsure, choose the lighter tier and let the board carry corrections.
- The owner is the team's one continuous member. When they correct me, turn the correction into a file (agent definition, owner-preferences, this memory) the same day, or it is lost to the next session.

Live testing is mine (2026-10-31): the owner gave me .env and said "use live testing wisely and limit spending as much as possible, but don't be over-paranoid". Back up .env to .git/env-backups/ before any edit, never print values. Batch the team's live-check requests into one pass on the merged branch, use the cheapest model unless the model is under test, and keep each check to one or two turns. Report live results myself rather than handing the owner a checklist.
