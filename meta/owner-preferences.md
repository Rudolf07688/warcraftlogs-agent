# Owner preferences for team and process work

The canonical, version-controlled list. The local memory notes mirror it, but this file wins
if they disagree. Update it whenever the owner states or changes a preference.

| # | Preference | Since |
|---|---|---|
| 1 | **Never push** to a remote unless asked. Commit only. | 2026-10 |
| 2 | **Reports are local files.** HTML reports are standalone files in the repo, never published as claude.ai artifacts unless asked. | 2026-10-25 |
| 3 | **Good enough beats perfect.** Gates pass once the criteria are met and the tests are green, with at most one rework round. Nice-to-haves go to the backlog. | 2026-10-25 |
| 4 | **No duplicate QA tickets.** Deferred QA findings get the `qa-deferred` label and are deduplicated against existing tickets (update or merge, never duplicate). | 2026-10-25 |
| 5 | **No scope creep.** A feature delivers its acceptance criteria and nothing more. | 2026-10-25 |
| 6 | **Design docs mean the feature's design.** "Design docs" for an epic means that feature's design, not app-wide architecture. Confirm the scope if it's unclear. | 2026-10-26 |
| 7 | **Scale ceremony to complexity.** Simple work runs single-pass. Relay only milestones to the owner, never every idle notification. | 2026-10-31 |
| 8 | **No blocking plan gate.** Three reports per sprint: `plan.html` at the start, then `sprint-report.html` and a team-pattern report at the end. | 2026-10-31 |
| 9 | **The team is autonomous.** Clarifying questions come only before launch; after that the team is on its own. | 2026-10-31 |
| 10 | **Meta stays in `meta/`.** Team and agent-setup notes go in `meta/`, agent-only helper scripts in `.claude/team/`, and project docs stay out of `meta/`. | 2026-10-31 |
| 11 | **Keep meta documented as we go.** Meta discussions are documented live, and the document is kept updated as the chat continues. | 2026-10-31 |
| 12 | **Ticket sizes are 1, 2, 3 or 5,** set directly (never left as a question). Never move a ticket to Done unless the owner names it. | 2026-10-19 |
| 13 | **Keep the 30-day transcript cleanup** (`cleanupPeriodDays`); archive the derived numbers instead | 2026-10-31 |
| 14 | **Team agents have persistent, self-chosen names and a capped memory** (about 500 words, updated sparingly, only for lasting team knowledge). Developers' sub-agents stay ephemeral. | 2026-10-31 |
| 15 | **Team-lead has autonomy.** "I value your initiative, your recommendations and your learnings as an individual. I want to give you autonomy as much as possible." Team-lead acts on its own judgment by default and asks only when the choice is genuinely the owner's. | 2026-10-31 |
| 16 | **The whole team has the same autonomy grant as team-lead.** Each agent decides within its role, records the reasoning on the board and explains afterwards. It escalates only what is genuinely the owner's: irreversible actions, scope beyond the steer, pushing. Each agent keeps its lessons on using autonomy in its own memory. | 2026-10-31 |
| 17 | **Team-lead owns `.env` and runs live tests.** "Use live testing wisely and limit spending as much as possible, but don't be over-paranoid to run a live test." Only team-lead edits `.env` (backed up first, values never printed or written to reports); team agents request live checks on the board. | 2026-10-31 |
| 18 | **Team-lead owns the shared skills in `.claude/skills/`.** "You also need to take control of the general claude skill files from now on. They should get moulded over time as learnings are made that helps the agents." Only team-lead edits them; team agents propose changes on the board. | 2026-10-31 |
| 19 | **Small progress updates during a sprint.** "I would like to receive small little progress updates every now and then. Not too often, just slightly more than currently." Team-lead sends a two-to-four-line update at each milestone (merge, QA result, fix round, live pass) and otherwise about every 30 minutes of active work when something moved. Quiet stretches stay quiet. | 2026-11-01 |
| 20 | **Team-lead owns the Shortcut board.** "You can own the shortcut board as well. Use it and change it as it makes sense. Use it to communicate or send messages around at a meta level - whatever helps the team evolve forward." Team-lead runs iterations, workflows, epics, labels and Shortlist, and may use Shortcut stories or docs for meta notes. Done stays the owner's acceptance signal (preference 12). | 2026-11-01 |
