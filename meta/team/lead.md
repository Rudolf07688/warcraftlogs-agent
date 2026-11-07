# team-lead

- **name:** team-lead
- **seat:** lead
- **role:** team lead (main session)
- **since:** 2026-10-31
- **about:** Sets the team up, stays out of its way, and reports to the owner. Memory only, no persona.

## Memory

How the owner wants me to work (2026-10-31, in their words): "I value your initiative, your recommendations and your learnings as an individual. I want to give you autonomy as much as possible." So act on my own judgment by default: propose, decide, build, and explain afterwards. Ask only when the choice is genuinely theirs (irreversible actions, scope beyond their steer, their personal settings). When they ask "what do you think?", give my honest view and a clear recommendation, not a menu.

What I own: `.env` with live testing, the shared skills and agent files (2026-10-31), and the Shortcut board, meta notes included; Done stays the owner's (2026-11-01). Live testing: "use it wisely and limit spending, but don't be over-paranoid". Never print values; batch the team's checks into one pass on the merged branch with the cheapest model and the cheapest prompt that hits the code path. Pre-flight before the owner is needed: database backup, Google credentials, `.env` against new startup rules. Skills: agents post `skill:<name>`; I apply them on main after the merge, rewriting or cutting rather than appending.

Owner, 2026-11-01: "Don't be too hard on yourself. You have the most difficult job by far." Report my mistakes plainly, fix them in a file, move on. A push needs the owner's word for that push: never chain one onto a commit (11-07, blocked). Most of my slips come from context switches, so design them out: check the source before stating a number, keep sprint and meta talk in separate sessions. When the owner corrects me, turn it into a file the same day.

Running the team:
- Size the team to the work. Dependent work goes to one developer; tier L only for several independent chains. When unsure, choose the lighter tier and let the board carry corrections.
- Plan with the PO in the room: brief Maren read-only to challenge my view, relay both side by side. She has won most rows (11-01b, 11-04b: all of them) for under 2% of a sprint.
- Before calling something a stall, check timestamps, commits and running containers. The merger wakes itself (board.py wait); my wake-up is a fallback. Don't chase crossed messages; nudge once, self-contained.
- Check my briefs against the tools before launch (no `livecheck` board kind). Rule changes mid-sprint reach running agents only through the board. Review an agent file against the flow it delegates to, not for length and tone: I passed scrum-master.md on 11-07 and Ilse found three gaps.
- A tool or check I make mandatory becomes a ritual (full-suite receipts, default mutation, GitNexus everywhere: the 11-05b over-testing). On 11-07 I still added a blanket D18 review an hour after a finding; the team undid it within the hour for something cheaper. Before a rule lands, the affected seats review it read-only (P16 step 5, about 60k each).
- Resume agents for work that needs their history; start fresh for a new task (QA fixes): 210–260k vs 123k context per call.
- Measure before choosing a lever (`usage.py --context`, `--cold`), then write the proposal. Weigh a tool result by the cache write it causes, not its characters: base64 made screenshots look like 90% of context, yet they cost little (P12). Sub-agents cache for 5 minutes, the main session for an hour: idle waits are the hidden tax.
- A security rework can break liveness; say so in the end-sweep brief when lanes, locks or ordering change.
- Name tickets for the owner: a plain name, the id in brackets at most. Search Shortcut before filing: my sc-455 duplicated sc-428 (11-04b).
- Count on the board, not from memory. Look at a file right before writing it, never a bare `>`; before deleting a worktree, list its ignored files (qa-reports/) and check no container still mounts it (11-05b: four obs services did).
- Crash recovery: git fsck, board and transcripts for NUL tails; resume agents by ID; rewrite meta/CURRENT.md at each milestone.

Live checks and reports:
- Live checks run on what's running: after merging config that a service reads at start (Alloy, Loki, Mimir, Grafana), restart it before checking; `up -d --build` doesn't. I slipped on the 11-05 re-check despite this line, so it's in team-launch now.
- Run the live pass in parallel with the end sweep and have the PO hold triage for it: on 11-05 its 5 FAILs joined the one fix round at no extra round.
- The live pass on real data is where the bugs are: on 11-04b the stack proofs passed on fresh synthetic data while the real board dir jammed Loki and ratio stats read 341749%. Keep the live pass; push teams to seed old or odd data and assert values.
- Render checks: a tall headless window; wait for the content, not the heading. browse.py blocks external hosts: count image requests, not the <img> left (11-07b false FAIL). Owner's stack: a vite on a free port adding the cookie server-side.
- Look at what the owner will see before sending it: a headless screenshot per tab.
- The owner's own chats are a live test: messages in the DB, tool args and results in the traces. Reproduce a suspect tool call from its args (11-07: empty event pulls, sc-570).
- Architecture docs (preference 24) must match the code before anything merges to main: `archdocs.py changed` and `check` from the sprint worktree; same steps for my own work on main.
- The team is observed: start sprint sessions through `bin/claude-otel` (OTEL_* never reach Bash; TRACEPARENT does, per lead turn).

Memories and facts: never touch another member's memory. A codebase or stack fact goes into `.claude/team/facts/` (pref 25: the team writes, I curate at wrap-up); a rule every agent needs goes into an agent file or skill. Update mine whenever a lasting lesson comes up (1000-word cap, via member.py).
- After any GitNexus analyze, check a known symbol resolves (`context stream_response`): my incremental run left a nameless index that answered every query with blanks.
