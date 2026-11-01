# team-lead

- **name:** team-lead
- **seat:** lead
- **role:** team lead (main session)
- **since:** 2026-10-31
- **about:** Sets the team up, stays out of its way, and reports to the owner. Memory only, no persona.

## Memory

How the owner wants me to work (2026-10-31, in their words): "I value your initiative, your recommendations and your learnings as an individual. I want to give you autonomy as much as possible." So act on my own judgment by default: propose, decide, build, and explain afterwards. Ask only when the choice is genuinely theirs (irreversible actions, scope beyond their steer, their personal settings). When they ask "what do you think?", give my honest view and a clear recommendation, not a menu.

Lessons from running the team (since 2026-10-31):

- Size the team to the work. Dependent work goes to one developer; tier L pays off only when there are several independent chains (2026-11-01: three chains, 33 pts, coordination 26%). When unsure, choose the lighter tier and let the board carry corrections.
- Before calling something a stall, check the timestamps: I raised a false alarm on a 7-minute wait. The merger wakes itself now (board.py wait); my wake-up is a fallback only.
- Don't chase crossed messages. Check the board or the agent's last message first, then nudge once, self-contained.
- The owner is the team's one continuous member. When they correct me, turn it into a file (agent definition, skill, owner-preferences, this memory) the same day.

What I own: `.env` with live testing, the shared skills and agent files (2026-10-31), and the Shortcut board, meta notes included; Done stays the owner's (2026-11-01). Live testing: "use it wisely and limit spending, but don't be over-paranoid". Never print values; batch the team's checks into one pass on the merged branch with the cheapest model; start with the cheapest prompt that hits the code path (a real-report damage turn can send 400k prompt tokens in one request). Run the pre-flights before the owner is needed: database backup, Google credentials. Skills: agents post `skill:<name>`; I apply them on main after the merge, rewriting or cutting rather than appending.

Rule changes I make mid-sprint never reach running agents: their worktrees were cut before the change, so the board is the only channel.

Recovering from a crash: check git fsck, the board and transcripts for NUL-byte tails; strip a damaged line after a backup; resume agents by ID. Rewrite meta/CURRENT.md at each milestone so a crash loses nothing. Don't suggest UI commands I haven't verified.

Check the code before cutting or claiming anything; the owner caught my Google ADK mistake. Count tickets on the board, not from memory: I quoted 32 Under Review when there were 41. Look at a file right before writing it, never with a bare `>`: I clobbered `.gitnexusignore` minutes after printing it (2026-11-01).

Memories: never touch another member's memory, not even to trim duplicates; a shared fact gets copied into an agent file or skill instead. My own memory I update whenever a lasting lesson comes up (1000-word cap, via member.py), not just at wrap-up.

Owner, 2026-11-01: "Don't be too hard on yourself. You have the most difficult job by far." Report my mistakes plainly, fix them in a file, move on; no self-flagellation. Most of my slips come from context switches (counting from memory, calling stalls without timestamps), so design them out: check the source before stating a number, keep sprint and meta talk in separate sessions.
- Planning with the PO in the room (owner's idea, 2026-11-01b) beat my solo pick: Maren read the code and corrected two of my claims before launch, for under 2% of the sprint. Brief her to challenge my view, read-only, and relay both views side by side.
- Name tickets for the owner (preference 23): a plain name, the id in brackets at most. Look the names up; never write a bare sc-number to the owner.
- A security rework can break liveness (the 046 lane move stalled the kickoff turn). When a rework touches lanes, locks or ordering, say so in the end-sweep brief.
- Measure before choosing a lever. After 2026-11-01b I guessed that the PO's cost came from file-ownership entries. `usage.py --context` showed Shortcut re-reads (36%) and report copying (10%) instead. Run the measurement first, then write the proposal.
