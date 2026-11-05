# Agent team optimisation

- **Started:** 2026-10-31
- **Updated last:** 2026-10-31
- **Status:** implemented on 2026-10-31. The team board is live, the agent files are
  rewritten around tiers, sub-agent developers and the board, and there's a team-lead
  launch skill. Next: verify all of it on the next real sprint.
- **Scope:** off-sprint and off-board. This covers the team setup in `.claude/agents/*.md`
  and how the main session runs the team. It isn't an app feature, so it gets no Spec Kit
  run and no Shortcut ticket.

## Goal

Cut the token cost per unit of delivered work. Match the team's size and process to how
complex the task is. Spend less on coordination and more on building. The team should run
as an autonomous unit that needs only a small owner input to steer it.

## Owner's starting position (2026-10-31)

- There's too much back-and-forth between agents. The ratio of tokens used to tasks
  completed is much too high.
- Token use and team size should depend on how complex the task is.
- Smaller tasks could be: the product owner defines the scope for the scrum master, and the
  scrum master works with a single developer to get it done quickly.
- Spec Kit stays the default. Below some threshold, a plain `/plan` followed by `/implement`
  is enough.
- Earlier the same day, the owner described **single-pass mode**: one developer goes
  straight through, the scrum master only manages tickets, and one QA sweep at the end
  fixes only the critical findings. See the memory note `feedback-sprint-ceremony-scale`.

## Evidence

**Method.**
- Per-agent token usage comes from the session transcripts:
  `python3 .claude/team/usage.py ~/.claude/projects/-home-rudolf-dev-warcraftlogs-agent/<session-id>`.
- "Weighted" means a rough price weighting: cache read 0.1×, cache write 1.25×, output 5×
  the base input price. It ignores the Opus/Sonnet price difference.
- Agents fall into five groups:
  - **Coordination:** the main session, the product owner and the scrum master.
  - **Build:** developers and their sub-agents.
  - **QA:** the QA sweeps and re-checks.
  - **Sync:** shortcut-sync.
  - **Probes:** capability probes.

### Baseline across the three agent-team sprints

| Sprint | Points | Model calls | Messages (scrum master) | Weighted cost (M units) | **Per point** | Coordination | Build | QA | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-25 | 23 | 1975 | 275 (140) | 61.0 | **2.65** | **55%** | 35% | 8% | First team sprint, 9 developers including one restart (dev-b-019 → v2), QA sweep plus a fix round with re-checks |
| 2026-10-26 | 20 | 1482 | 250 (118) | 43.6 | **2.18** | **42%** | 49% | 8% | Two design docs and three builds; owner plan gate; QA sweep, no fix round |
| 2026-10-31 | 21 | 990 | 160 (76) | 29.2 | **1.39** | **41%** | 58% | 0% | Fast-tracked halfway; no QA sweep |
| 2026-10-31b | 21 | 757 | 11 (no SM) | 17.5 | **0.83** | **29%** | 52% | 18% | PO + 2 devs, tiers M + S, autonomy grant (D15); QA sweep + one fix round; machine crash mid-sprint |
| 2026-10-31c | 19 | 628 | 9 (no SM) | 17.5 | **0.92** | **38%** | 48% | 12% | PO + 2 devs (Ansel on opus), tiers M + S; QA sweep + one split fix round; 78 min steer to wrap; lead share includes skills prune + live pass |
| 2026-11-01 | 33 | 1256 | 40 (SM 15) | 39.0 | **1.18** | **26%** | 58% | 16% | Tier L: PO + SM (Ilse) + 3 devs (Nils new); P7 trial 4% inside QA; split fix round; ~3 h 10 min steer to wrap |
| 2026-11-01b | 20 | 833 | 7 (no SM) | 20.5 | **1.03** | **26%** | 56% | 18% | Tier M: PO + 2 devs; first P9 trial; PO in planning (0.35 M); P7 5% + split fix round; 1 h 36 min steer to wrap |
| 2026-11-02 | 20 | 922 | 20 (no SM) | 25.3 | **1.27** | **16%** | 68% | 16% | Tier M: PO + 3 devs, fully autonomous (no owner turn after the steer); P10/P11 first trial; devs resumed for P7 rework *and* QA fix (210–260k context/call) → build 0.86/pt; 1 h 33 min steer to PO report |
| 2026-11-04 | 23 | 958 | 15 (no SM) | 26.9 | **1.17** | **29%** | 53% | 18% | Tier M: PO + 2 devs + Tomas on docs; first infra sprint (telemetry 1), planned with PO the same morning; security review at hand-off + QA fix round in fresh agents (0.81 vs 7.65 build for Nils); a PO-unwatched question cost 55 min; 2 h 54 min steer to PO report |
| 2026-11-04b | 24 | 1168 | 8 (no SM) | 31.2 | **1.30** | **31%** | 59% | 10% | Tier M: PO + 3 devs (Tomas on browser, then docs), planned with PO in the room (her view won every row); first sprint observed by its own telemetry (claude-otel); owner added 2 panels mid-sprint; security review at hand-off; live pass found 5 issues the synthetic stack proofs missed (one was my screenshot artifact); QA fix rounds fresh (Ansel 3.68, Nils 1.95, both Read-heavy on screenshots); 2 h 42 min steer to PO report |

**Caveats.**
- The main-session transcripts include some non-sprint work. On 10-25 that was writing the
  agent definitions themselves; on 10-31 it's the start of this discussion. This inflates
  the coordination share a little.
- 10-31 skipped QA, so about 8% of the drop in cost per point comes from that.

**Readings.**
- Cost per point has fallen about 48% over the three sprints, and messages about 42%.
  The two process corrections (the first sprint's learnings, then the fast-track) are
  visible in both numbers.
- Coordination is still about 40% of the cost. Build is the only part that should grow
  with the work.
- The scrum master is the largest single messager in every sprint (140 → 118 → 76 messages).

### Sprint 2026-10-31 per agent

| Agent | Model calls | Output tokens | Context re-read (cache) | Cache writes | Messages sent |
|---|---|---|---|---|---|
| Main session (team-lead, relaying) | 174 | 67k | 26.8M | 0.21M | 23 |
| Scrum master | 179 | 106k | 29.7M | 0.76M | **76** |
| Product owner | 78 | 65k | 14.7M | 1.67M | 13 |
| **Coordination subtotal** | **431** | **238k** | **71.2M** | **2.65M** | **112** |
| dev-a-032 (Opus, high) | 168 | 165k | 48.9M | 0.42M | 12 |
| dev-b-035 (Opus, medium) | 164 | 140k | 45.0M | 0.38M | 16 |
| dev-b-034 (Opus, medium) | 116 | 98k | 22.8M | 0.27M | 10 |
| dev-a-033 (Sonnet, high) | 81 | 59k | 11.7M | 0.21M | 10 |
| Sub-agents (034 frontend, shortcut-sync) | 19 | 13k | 1.3M | 0.19M | 0 |
| **Builder subtotal** | **548** | **475k** | **129.6M** | **1.47M** | **48** |

The sprint added 8.1k lines in about 1h 20m. 3.4k of those lines were Spec Kit documents
across 37 files.

## Findings

1. **Every message costs at least one more model turn.** Messages from the product owner to
   a developer go through the scrum master, so each takes two hops. Each agent that goes
   idle also notifies the main session, which adds a third turn per exchange, at about 150k
   tokens of context each time.
2. **The ACK protocol doubled the traffic.** It was added to stop agents stalling on crossed
   messages. In practice, each crossing still produced a re-send plus an ACK, and there
   were about 8 crossings on 10-31.
3. **Long-lived coordinators get more expensive over time.** By the end of 10-31 the scrum
   master re-read about 165k tokens of context per turn, however small the message it was
   handling.
4. **Splitting dependent work created costs of its own.** 033 and 035 both depended on 032,
   so the provider work ran in sequence anyway. Splitting it across three developers still
   added:
   - a contract hand-off
   - extra file-ownership negotiation over `vertex.py` and `README.md`
   - a red test after the merges

   One developer doing epic 248 end to end would have avoided all three.
5. **Spec Kit's document volume is heavy for small work.** About 40% of the lines added on
   10-31 were Spec Kit documents.
6. **Gates without real decisions behind them.** Most gates passed on the first round, but
   each one still cost a round of messages and several caused crossings.
7. **Point-to-point messages carry no ordering.** Decisions reach agents in whatever order
   their mailboxes drain. An agent has no reliable way to know that a later decision
   overrides an earlier one, which is where the crossings and re-sends come from.

## Decisions (owner, 2026-10-31)

- **D1. The plan doesn't block.** The product owner always writes the plan as a
  well-formatted HTML report at the start of the work, in the style of the sprint review
  report. The team carries on without waiting for the owner to review it.
- **D2. The product owner decides the complexity tier** and runs the work accordingly.
- **D3. Three owner-facing reports per sprint:**
  - the plan, at the start
  - the sprint review, at the end
  - an analysis of the team's patterns during the sprint, at the end, with the same kind of
    data as this document (`team_usage.py`)

  The plan and the review are about the project work, so they go in `sprints/<date>/`. The
  team-pattern analysis is about the team, so it goes in `meta/sprints/<date>/` (D7). All
  three are local HTML files.
- **D4. The team is autonomous.** The owner gives only a small input to steer the direction
  or scope of the next piece of work. The main session may ask the owner clarifying
  questions *before* launching the team. After launch, the team is on its own.
- **D5. The product owner stays in every tier,** as the entry point that turns the owner's
  steer into scope, a tier and a plan. This follows from D2 and D4.
- **D6. When only one developer is working, it owns its own board tickets.** The
  original intent, that the scrum master is the single point of contact with the board,
  still holds whenever there's more than one developer.
- **D7. A `meta/` directory holds all team and agent-setup notes,** kept separate from
  project documentation. This document and the original team prompt moved there.
  Agent-facing helper scripts live in `.claude/team/` instead, since humans don't need to
  see them.
- **D8. Build the team board (P4), including the automatic hook.** Done on 2026-10-31;
  see the P4 section for what was built.
- **D9. Adopt P5.** Developers are background sub-agents by default. A messaging teammate
  is used only when a role expects more than about 3 live two-way exchanges.
- **D10. The scrum master exists only in tier L.** In tiers S and M the product owner
  absorbs its duties: launching developers, ticket hygiene across features, merging, and
  the protected files.
- **D11. Rewrite the agent files and add a launch checklist,** and commit what's built.
  Done on 2026-10-31; see "What changed in the agent setup".
- **D12. Don't raise `cleanupPeriodDays`.** Transcripts keep the 30-day default, so the
  numbers we need are archived to `meta/sprints/<date>/usage.txt` instead.
- **D13. Persistent team identities with a capped memory.** Each team agent picks its own
  name, and the name survives respawns. Each one keeps a curated memory of about 500
  words, updated sparingly and only with knowledge that helps the team in the long run.
  Developers' own sub-agents stay ephemeral and unnamed. See P6.
- **D14. Team-lead gets a `lead` seat: a memory without a persona.** It's a first-person,
  500-word memory of how the lead runs the team, kept in git where the team can read it.
  Team-lead has no name, because the owner already knows who it is. The reasoning: the
  owner is the team's one continuous member, and the lead's lessons used to live only in
  conversations until the owner corrected them.

- **D15. The whole team gets the lead's autonomy grant.** Owner, 2026-10-31, before sprint
  2026-10-31b: each agent decides within its role and explains afterwards; escalations only
  for irreversible actions, scope beyond the steer, pushing. The sprint's second goal is the
  team learning to operate this way. Owner preference 16; an "Autonomy" section in the three
  agent files.

- **D16. Team-lead owns `.env` and live testing.** Owner, 2026-10-31: "You will need to take
  control of the `.env` file from here on out to be able to do live testing. Use live testing
  wisely and limit spending as much as possible, but don't be over-paranoid." Rules: only
  team-lead edits `.env`; a backup goes to `.git/env-backups/` (never committed) before each
  edit; secret values are never printed, logged or written to reports. Developers and the
  product owner can't reach `.env` from their worktrees, so they request a live check on the
  board (`question`, key `live-check:<feature>`) with the exact steps, and only when tests
  can't settle the question. Team-lead batches the checks into one pass on the merged sprint
  branch at the end of the sprint: cheapest model unless the model is under test, one or two
  turns per check, the WCL cache on, and no guide-pipeline runs unless the guide is the thing
  being tested. Owner preference 17.

- **D17. Team-lead owns the shared skills (`.claude/skills/`).** Owner, 2026-10-31, at the
  start of sprint 2026-10-31c: "You also need to take control of the general claude skill
  files from now on. They should get moulded over time as learnings are made that helps the
  agents." Rules: only team-lead edits skills. A team agent that was misled by a skill, or
  learned something the next agent needs, posts a board `notice` with key `skill:<name>`
  (what to change and the evidence). Team-lead applies the batch at wrap-up, on main after
  the merge, so the next sprint's worktrees get it. Edits keep skills lean: rewrite or cut
  rather than append, following `skill-writing-best-practices`. Tool-generated skills
  (`speckit-*`, `gitnexus-*`) can be overwritten by an upgrade, so local changes there go in a
  marked "Local learnings" section and are re-checked after each upgrade. Agent memories
  hold what one member learned; skills hold what every agent doing that task should know.
  Owner preference 18.
- **D18. Adopt P7: a scoped security review at each security-core hand-off.** Owner,
  2026-11-01, after the sprint 2026-11-01 wrap-up: "yes adopt P7". The merger (scrum master
  in tier L, product owner otherwise) runs one `qa-security` pass on the feature diff before
  merging, with a prompt written from the code and design, never from the developer's notes.
  Security-core now also covers any shared cache, single-flight or Redis key path. The
  developer fixes Highs and Mediums in its one rework round; the end sweep stays the gate.
  In `product-owner.md` §3 and `scrum-master.md` §4.
- **D19. Team-lead owns the Shortcut board.** Owner, 2026-11-01: "You can own the shortcut
  board as well. Use it and change it as it makes sense. Use it to communicate or send
  messages around at a meta level - whatever helps the team evolve forward." Covers
  iterations, workflows, epics, labels, Shortlist and meta notes on the board (stories or
  Shortcut docs). Done stays the owner's acceptance signal. Owner preference 20.

## Proposals under discussion

### P1. Complexity tiers (the product owner chooses, per D2)

| Tier | When | Who | Process |
|---|---|---|---|
| **S** | ≤ 3 points, one area, no change to the data model, security or tenant data | Product owner + one developer | `/plan` → `/implement`. The developer moves its own tickets. |
| **M** | Most features (for example the 10-31 epic) | Product owner + one developer per independent stream | Spec Kit in a single pass with no mid-way gates. One QA sweep at the end; fix only the critical findings. |
| **L** | Two or more independent streams sharing files, an ambiguous design, or a migration together with security work | Product owner, scrum master, developers | Spec Kit with gates, made leaner |

- **Open:** whether the scrum master is needed in S and M. Its value is arbitrating file
  ownership between parallel developers and running gates. With one developer per
  independent stream there's little to arbitrate.

### P2. Run developers as sub-agents, not messaging teammates

- **The change:** the coordinator launches each developer as a sub-agent with a complete
  brief. The developer's hand-off comes back as its result.
- **What that removes:** mailbox traffic, crossed messages, ACKs, spawn and stop requests,
  and idle relays to the main session.
- **The trade-off:** a developer can't be messaged mid-run. P4 addresses this, because the
  developer can still *read* the message board.

### P3. Fewer messages wherever messages remain

- One self-contained message per gate.
- No ACK protocol.
- The main session relays only milestones and real decisions.

### P4. Team board: implemented 2026-10-31

This is an append-only, chronological board that every agent can post to. The latest entry
on a topic key wins, so agents always know which decision came later. New entries reach
every agent automatically.

- **Tool:** `.claude/team/board.py`, Python standard library only. The commands:

  | Command | What it does |
  |---|---|
  | `post <kind> "text" --as NAME [--key K] [--supersedes N] [--ref R]` | Adds an entry |
  | `current` | The effective state: the latest entry per key, plus open un-keyed decisions and questions |
  | `log --since N` | The raw history |
  | `read --as NAME` | Shows the entries this agent hasn't seen |
  | `init NAME` | Opens a board for a sprint |
  | `close --export PATH` | Exports the board and closes it |
  | `status` | Says which board is active |

- **Storage:** `<git common dir>/team-board/<name>.jsonl`. Every worktree of the repo
  resolves the same file, with no path configuration and nothing tracked in git. A file
  lock keeps concurrent posts safe; 8 parallel posts produced unique, ordered ids.
- **The automatic hook:** a project `PostToolUse` hook on every tool, in
  `.claude/settings.json`, runs `board.py hook`. After each tool call it adds the caller's
  unread entries from *other* agents as `[team-board] …` context, capped at 15 entries or
  3.5k characters. It is silent when nothing is new or no board is active, and it never
  fails a tool call.
- **Verified on 2026-10-31:**
  - Hooks fire inside sub-agents, with `agent_id` and `agent_type` in the hook input.
  - Injected context reaches a sub-agent: a Haiku probe quoted it back word for word.
  - The main session receives entries too, as `team-lead`.
  - A named teammate's identity is read from its id (`a<name>-<16 hex>`). An unnamed
    sub-agent's identity is learned from the `--as` on its first board command, after
    which its own posts are filtered out.
- **Agent rules:** a "Team board" section in `product-owner.md`, `scrum-master.md` and
  `developer.md`. Decisions, changes, hand-offs, merges and blockers go on the board, with
  keys for anything that can change. `SendMessage` is used only to make someone act now.
  No ACK or status-only messages.
- **Lifecycle:** the main session runs `board.py init sprint-<date>` at launch. At
  wrap-up it runs `board.py close --export meta/sprints/<date>/board.jsonl`, which feeds the
  D3 team-pattern report.
- **Caveats:**
  - Worktrees only get the hook and the script once they're committed, because worktrees
    check out committed files.
  - An unnamed sub-agent sees the whole board (up to the cap) once more, when it first
    posts.
  - The board doesn't wake an idle agent. That's intended: a direct message does that.

### P5. Teammates or sub-agents? A proposed threshold

What each option costs, using the 10-31 numbers:

- **Each message to a messaging teammate** costs the receiver a full turn, about 150k tokens
  of context re-read. It also costs an idle notification to the main session, which is
  another turn of about the same size. That's roughly 30–35k weighted units per message.
- **Starting a fresh sub-agent** costs building a new context: the brief plus the code it
  reads, roughly 40–60k tokens of cache writes, or about 50–75k weighted units.
- **With the board in place, decisions and corrections no longer need messages.** They
  reach a running sub-agent through the hook. A teammate's remaining advantages are that it
  can answer a question mid-run and that it keeps its context across rework rounds. A
  background sub-agent can also be resumed, via `SendMessage` to its id, so rework doesn't
  necessarily need a fresh context.

**Proposal:**
- **Default:** developers are background sub-agents launched directly by the coordinator.
  This also removes the spawn and stop round trips through the main session and the idle
  relays.
- **Use a messaging teammate only when a role expects more than about 3 genuine two-way
  exchanges during its run** that can't be written as board entries. Examples:
  co-designing an interface live with another developer, an iterative design doc with
  several review rounds, or a long-lived role such as the product owner.
- **In practice:** the product owner stays a teammate. It's long-lived and receives your
  steer. The scrum master, in tier L only, is a teammate. Developers are sub-agents in S
  and M, and in L unless the plan names a live co-design need.
- **To verify:** whether a sub-agent can launch its own sub-agents (depth 2), for
  developers who want to fan out; and that a coordinator's `SendMessage` to a sub-agent's
  id resumes it cleanly for rework.

### P7. Scoped security review at hand-off for security-core work (adopted as D18, 2026-11-01)

- **Evidence:** in both autonomy sprints, the two QA Highs sat in security-core code
  (2026-10-31b: the srcset bypass and the retry wait; 2026-10-31c: trusting query text over
  the WCL response). The authors' bypass attempts each found real holes, but missed the
  class QA found. Each time the fix needed a second developer launch, with the context
  rebuilt from scratch.
- **Proposal:** when a brief marks a feature security-core (tenant visibility, auth, RLS,
  rendering untrusted output), the product owner runs `qa-security` scoped to that
  feature's diff at hand-off, while the developer is still live. The developer fixes it in
  the same run. The end-of-sprint sweep stays as the gate.
- **Measure:** Highs still found by the end sweep, and the cost of the rework round
  compared with the scoped review (about 0.2 M units).
- **Result (sprint 2026-11-01):** four runs at 0.31–0.53 M units each (1.61 M, 4% of the
  sprint). They found 2 Mediums and about 12 Lows, all fixed or ticketed, and no visibility
  bypass. The end sweep still found one cross-workspace High, in 045 (cache single-flight),
  which was not on the P7 list. The independent pass the scrum master prompted from the code
  found the two most useful issues; the developer-prompted pass anchored on the
  developer's model.
- **Recommendation (team-lead, Ilse, Maren):** adopt. The merger (scrum master in tier L,
  product owner otherwise) writes the prompt from the code and design, never from the
  developer's notes, one run per security-core hand-off. Widen security-core to any change
  to a shared cache, single-flight or Redis key path. The owner agreed; see D18.

### P8. Report team-lead spend by activity (2026-11-01)

The main-session figure mixes sprint coordination, owner meta work and the live pass. In
2026-10-31c that pushed coordination from 29% to 38%, although the team itself
coordinated less (9 messages). Team-lead posts `phase:<meta|live|wrap>` notices on the
board, and `usage.py` splits the main session at those timestamps. The baseline then
compares team coordination only.

### P9. Tools over rules (implemented 2026-11-01, trial next sprint)

- **Evidence:** "green that wasn't" recurred for three members although `developer.md` said
  to read the summary line; about half of the developers' memory lines were hand-written
  recipes (clean suite run, throwaway Postgres, mutation check, GitNexus false alarms,
  guard tests); 19 of 40 messages last sprint were team-lead wake-ups. Rules in prose don't
  hold under pressure, and members memorise what the toolkit should do.
- **Built:** `check.py` (clean run, reads the summary, receipt per git tree, `verify --index`
  lets a merger reuse a receipt for an identical merged tree; refuses a tree with `.env`),
  `pg.py`, `mutate.py` (verified restore, crash-safe backup), `guards.py` (6 guards found
  from the tests themselves), `board.py wait` (probe: a sub-agent's own background job
  re-invokes it ~3 s after it exits), `member.py lint` (read-only; preference 21 holds),
  `.gitnexusignore` (GitNexus skipped `wcl_agent/cache/` by its default `cache` rule).
- **Measured cost:** none of it runs in the per-tool-call hook (40 ms). Full suite 101 s in a
  clean worktree; `pg.py up` 6 s; `wait` polls a file every 3 s.
- **Found on the way:** sc-336, the suite reads the real `.env` in the main checkout
  (21 failures, live Model Garden calls). It was a known workaround in team-launch, never a
  ticket.
- **Measure next sprint:** "green that wasn't" count (target 0); team-lead wake-ups (target
  only fallbacks); merges that reused a receipt; memory lines flagged by `lint` before and
  after wrap-up.
- **Result (2026-11-01b):** held on every measure: 0 green-that-wasn't, 0 wake-ups, 1 of 3
  merges reused a receipt (the other two were mixed trees, as designed), and lint 14 → 3.

### P10. Lighter product-owner admin (owner go 2026-11-01; built, trial next sprint)

- **Evidence:** Maren's delivery run is the largest coordination item: 3.45 M of 5.39 M,
  0.17 M per point, and 43% of it is cache writes (1.19 M), meaning new context. Against
  the earlier tier-M sprints (0.83, 0.92), this sprint's 1.03 per point is higher, and
  P7 (0.05/pt) plus the planning run (0.02/pt) explain only part of the gap.
- **Measured before changing anything** (`usage.py --context`). Her new context came from:
  - Shortcut reads: 36%. These were full story reads (about 5,700 characters each) of
    tickets the planning run had already read, which in turn spent 89% of its context on
    Shortcut.
  - Developer hand-offs: 18%. Needed.
  - Source reads: 17%. Her judgement work: briefs and the flake diagnosis.
  - Board: 10%.
  - Copying old HTML reports for their style: 10%, plus about 60k characters of markup
    she re-typed, at the 5× output weight.

  Her 32 per-file `owner:` entries (a third of the board) cost her little, but the hook
  delivers every entry to every agent. Shortcut *writes* are cheap (about 100 characters each).
- **Built / changed:**
  - `report.py build` wraps a body fragment in the shared shell (`report-shell.html`).
    It rebuilds the 2026-11-01b review byte for byte. `report.py classes` prints the
    class vocabulary.
  - `product-owner.md`:
    - Read each ticket once; `plan.md` is the ticket source after that.
    - Reports go through `report.py`, without opening an old one.
    - One `owner:<glob>` per stream; per-file keys only for shared files.
    - Ticket writes go in one batch per milestone.
  - The team-launch skill builds the team report with `report.py` and reads `--context`.
- **Measure next sprint:** Maren's delivery cost per point (0.17, target ≤ 0.12); her Shortcut
  share (36%, target < 15%); html share (10%, target ≈ 0); `change` entries per stream.

### P11. Live checks judge the answer (built 2026-11-01, owner go)

The live pass counted a turn as passed when an answer came back. "Agent picks the wrong
last boss kill" (sc-365) surfaced only because two turns disagreed.
- `livecheck.py` now judges each turn against `EXPECT`: PASS, FAIL, ANSWERED (no
  expectation) or EMPTY. It prints a `LIVE RESULT` line and exits 1 on a FAIL or EMPTY.
- Expectations come from the stored report (`livecheck.py --facts <code>`), never from a
  model. For the test report the last boss kill is fight 32, Ula'tek heroic.
- The chart prompt now asks the agent to name the boss, so it can be checked.
- Measure: wrong answers caught by the run rather than by eye.

### P12. Where Telemetry 2's extra cost went (measured 2026-11-05; levers 1–2 built, owner go, trial next sprint)

Owner asked to measure before choosing a lever. Telemetry 2 (11-04b) cost 31.2 for 24 pts;
at 11-01b's 1.03/pt it would have cost 24.7. Against 11-01b (20.5), by bucket:

| Bucket | 11-01b | 11-04b | Change |
|---|---|---|---|
| Build (developers) | 9.6 (0.48/pt) | 9.9 (0.41/pt) | +0.3, cheaper per point |
| QA fix rounds | 1.8 | 5.6 | **+3.8** |
| Docs close-out (new since 11-04) | 0 | 2.8 | **+2.8** (first pass 1.8, delta pass after the fixes 1.0) |
| Product owner | 3.8 | 6.2 | **+2.4** |
| Team-lead | 1.3 | 3.3 | +2.0 (owner's two panels with screenshots ≈ 1.7, live pass ≈ 1.0) |
| QA sweeps, security reviews, sync | 4.0 | 3.4 | −0.6 |

Readings:
- **The build is not the problem**; everything after it is. The fix rounds, the docs
  pass and the PO's waiting all grew.
- **Screenshots are not the cost.** By characters, `Read` was 74–97% of new context for
  the lead, PO and fix rounds, but base64 overstates images. Charged by the cache write
  they caused, image reads cost 0.14 (Nils's fix round) and 0.31 (lead). Closes the
  11-04 lever "measure screenshot Read cost".
- **Cold caches are a standing tax of about 10%.** Sub-agents keep a 5-minute prompt
  cache (gaps of 5.2–5.6 min already went cold). Each wake after a longer idle rewrites
  the whole context: 2.5 (11-01b), 3.2 (11-02), 4.2 (11-04), 3.2 (11-04b). Maren is most
  of it: on 11-04b she woke cold 7 times after 5–32 min idle, rewriting 130–285k each,
  2.05 of her 6.16. Developers pay it when resumed (Tomas's delta pass, Ansel's resume).
- **The docs pass ran twice** because it started in parallel with the fix rounds and
  needed a delta pass once they merged.
- Ansel's fix round (nine items, 147 calls, 18:26 to past 19:33) was as large as a build
  stream; Nils's took 96 calls.

Levers, by expected saving per sprint:
1. **Keep the PO's cache warm** (≈ 1.5 first estimate; ≈ 0.7 after the probe, see below). While she waits longer than 5 minutes, she
   waits in slices of ≤ 4.5 min (`board.py wait --timeout 270`, re-armed on timeout). A
   warm wake at ~200k costs ≈ 0.02 against ≈ 0.3 for a cold one. First check whether
   sub-agents can get the 1-hour cache the main session already has; that would be the
   cleaner fix.
2. **Docs close-out once, after the fix rounds merge** (≈ 1.0). Drop the parallel first
   pass plus delta pass.
3. **Smaller fix rounds** (to measure, not yet a rule). Split a round above ~5 items into
   two fresh agents, as 11-01 did.
- Measure next sprint: cold-call weight (target < 1.5), the PO's cost per point (0.26 on
  11-04b), docs close-out (≤ 1.8), fix-round cost per item.
- **Built (owner: "let's get those implemented so we can see if it helps"):**
  - The 1-hour cache, checked first: the transcripts confirm the main session writes 1-hour
    cache and every sub-agent 5-minute. Switching all sub-agents to one hour is not worth it
    even where possible: a 1-hour write costs 2× base against 1.25×, so developers would pay
    about as much more as the PO saves. The targeted warm wait wins.
  - `board.py wait --since N --warm`: times out after 270 s with exit 3; the re-arm is the
    identical command (`--since` is required, so nothing is missed). After `--warm-for`
    minutes (default 25) it exits 2. Tests in `backend/tests/test_team_board.py`.
  - Probe (haiku sub-agent, 2026-11-05): a tick re-invokes the agent and the cache stays
    warm (after a 4.5 min gap: 43.5k read, 578 written). The first version cost 3 calls per
    tick because the agent read the output file to find the printed re-arm command; with the
    identical-command re-arm a tick is 2 calls. Break-even: a cold wake rewrites C at 1.25×,
    a tick reads C twice at 0.1×, so about 6 ticks (≈ 25 min) equal one cold wake; hence the
    25-minute window. Replayed on Maren's 11-04b gaps (5–32 min) that saves about 0.7, not
    the 1.5 first estimated (that assumed 1 call per tick). A `Monitor`-driven heartbeat could
    make a tick 1 call; untested.
  - `product-owner.md` §3 and `scrum-master.md`: arm waits with `--warm`; on a tick only
    re-arm and end the turn; keep one warm wait armed while their own background agents run.
  - `product-owner.md` close-out step 5 and team-launch: the architecture docs pass runs
    once, after every fix round is merged.
  - `usage.py --cold`: cold-cache calls per agent (11-04b reads 3.22, matching the manual
    count); team-launch wrap-up reads it.
  - Lever 3 (split fix rounds above ~5 items) stays a measurement, not a rule.

## What changed in the agent setup (2026-10-31)

| Before | After |
|---|---|
| The main session spawned every named developer on a scrum master `SPAWN-REQUEST`, then stopped it on a `STOP-REQUEST` | The product owner (tiers S and M) or the scrum master (tier L) launches developers directly as background **sub-agents**. A hand-off comes back as the sub-agent's result. |
| Every feature ran gated Spec Kit (spec sign-off, plan grant, tasks gate, ACKs) | **Tiers.** S: a short plan, then implement. M: a single Spec Kit pass, with the developer answering its own clarify questions on the board. L: gated Spec Kit under a scrum master. |
| Decisions were relayed by message and logged by hand in `decisions.md` and `log.md` | Decisions, changes, grants, hand-offs and merges go on the **team board**, keyed so that the latest entry wins. The hook delivers them to every agent. |
| File ownership lived in `ownership.md`, run by the scrum master | `owner:<path>` keys on the board. Footprints are set in the brief. |
| The scrum master was always present and routed every message | The scrum master only exists in tier L. The product owner merges and keeps tickets tidy in S and M. |
| An owner plan gate blocked implementation | The plan is written as `plan.html` and doesn't block (D1). |
| Merges ran the suite on the feature branch | Merges rebase first and run the suite on the **rebased** result, a lesson from 035. |
| Reports: plan, sprint review | Plan (`plan.html`), sprint review (`sprint-report.html`), and a team-pattern report from team-lead (`meta/sprints/<date>/team-report.html`) |

**Files:** `.claude/agents/product-owner.md`, `scrum-master.md` and `developer.md` were
rewritten. `.claude/skills/team-launch/SKILL.md` (new) is the main-session checklist for
before launch, the quiet watchdog role, and wrap-up.

### P6. Persistent identities and memory: implemented 2026-10-31

**The goal:** let the team build a working relationship over time. Each agent persists
through respawns as the same named member, with its own small, curated memory. Its
*context* is still fresh on every launch.

- **Seats** are stable slots: `po`, `sm`, `dev-1`, `dev-2` and so on. Whoever is launched
  into a seat inherits its name and memory. The product owner reuses developer seats so
  that names carry over, and prefers a seat whose memory fits the work.
- **Tool:** `.claude/team/member.py`. The commands:

  | Command | What it does |
  |---|---|
  | `me --seat S` | The first action of every run. It prints who you are and your memory, or invites the first holder to choose a name. |
  | `claim` | Takes a seat. Names are one capitalised word and must be unique. |
  | `remember` | Replaces the whole memory, with a hard cap of 500 words; an over-cap write is rejected and nothing is saved |
  | `roster` | Lists everyone on the team |

- **Storage:** `meta/team/<seat>.md` in the **main checkout**, resolved through the git
  common dir. Every worktree reads and writes the same copy, outside any feature branch.
  Team-lead commits the files at wrap-up.
- **Memory discipline** (in every agent file):
  - Update it at most once per run, at the end. Often the right choice is no change.
  - Keep only lasting codebase and tooling lessons, how a teammate works best, and what the
    owner cares about.
  - Never task status, or anything already recorded elsewhere.
  - At the cap, cut the least useful line before adding one.
- **The lead seat** (D14): `claim --seat lead` takes no name and stays `team-lead`. The
  `team-launch` skill reads this memory first and updates it at most once per sprint. The
  SessionStart hook also injects it during an active meta discussion.
- **Board names:** `--as` is now the member's own name in lower case. The board hook
  learns each agent's name from its first post.

## Open questions

1. **Verification on the next real sprint.**
   - Does the board actually reduce messages? Measure it with `usage.py`, against a
     coordination share of about 41%.
   - Do sub-agent developers stay within their footprint without gates?
   - Is the step-boundary board reading enough, or does the hook carry it all?
2. **Tier boundaries:** are they in the right place? Review them after a sprint that
   contains all three tiers.
3. **Memory quality:** after a few sprints, review whether the memories hold lasting
   knowledge or drift into task notes, and whether 500 words is the right cap.

## Change log

- **2026-10-31:** Document created. It records the 10-31 evidence, findings 1–6, P1–P3 and
  open questions.
- **2026-10-31:** The owner answered the first four questions, recorded as D1–D5. Added the
  three-sprint baseline: cost per point 2.65 → 2.18 → 1.39 and coordination share
  55% → 42% → 41%. Added finding 7, proposal P4 (the message board) and new open
  questions 1–3.
- **2026-10-31:** The owner answered: D6 (a single developer owns its tickets), D7 (the
  `meta/` directory), and D8 (build the board with the automatic hook). Moved this document
  and the original team prompt docs to `meta/`, and the usage script to
  `.claude/team/usage.py`. Built and verified the team board (P4) and wired it into the
  three agent files. Added P5, the sub-agent vs teammate threshold, and replaced the open
  questions.
- **2026-10-31:** The owner agreed D9 (P5 threshold), D10 (the scrum master only in tier L)
  and D11 (rewrite and commit). Verified that a sub-agent can launch its own sub-agent
  (depth 2). Rewrote the three agent files, added the `team-launch` skill, and recorded the
  before/after table. Open questions are now about verification.
- **2026-10-31:** Added the persistence system for meta knowledge:
  - `meta/CURRENT.md` (working memory), re-injected by a SessionStart hook
    (`.claude/team/meta_context.py`)
  - a META block in `CLAUDE.md`
  - `meta/owner-preferences.md` (canonical) and `meta/sessions.md` (the session ledger)
  - archived per-sprint usage in `meta/sprints/<date>/usage.txt`, because transcripts are
    deleted after 30 days

  The layers are documented in `meta/README.md`.
- **2026-10-31:** The owner declined raising the cleanup period (D12) and asked for
  persistent, self-named team members with a capped memory (D13). Built
  `.claude/team/member.py` and seats, wired an identity-and-memory section into the three
  agent files and `team-launch`, and added P6.
- **2026-10-31:** The owner asked whether team-lead wants its own identity and memory, and
  agreed with my answer (D14): a memory, but no persona. Added the `lead` seat to
  `member.py` (and fixed `remember -` for stdin), seeded `meta/team/lead.md` with seven
  lessons from sprint 2026-10-31 (273 words), and wired it into `team-launch` and the
  SessionStart hook.
- **2026-10-31:** The owner gave team-lead autonomy ("I value your initiative, your
  recommendations and your learnings as an individual"). Recorded it in `meta/team/lead.md`
  and as owner preference 15.
- **2026-10-31:** Before sprint 2026-10-31b the owner extended the autonomy grant to the
  whole team (D15, preference 16) and scoped the sprint to hardening and QA debt, so the
  team can concentrate on learning to work autonomously.
- **2026-10-31:** The owner handed team-lead control of `.env` and live testing (D16,
  preference 17), mid-sprint 2026-10-31b. Posted on the board so the team can request checks.
- **2026-10-31:** Sprint 2026-10-31b closed: 21/21 pts, cost per point 0.83 (from 1.39),
  coordination 29% (from 41%), with a QA sweep and one fix round included. Zero escalations
  under the autonomy grant; both QA Highs came from unreviewed tier-S security fixes. First
  team-lead live pass (D16). Team report: `meta/sprints/2026-10-31b/team-report.html`.
- **2026-10-31:** The owner handed team-lead the shared skills (D17, preference 18) at the
  start of sprint 2026-10-31c. Agents propose changes on the board (key `skill:<name>`);
  team-lead applies them at wrap-up. Added to the three agent files and the team-launch
  wrap-up.
- **2026-11-01:** First skills pass under D17: pruned the skills for stacks the project doesn't
  use (A2A protocol, agentgateway, Agno, LangChain/LangGraph, Kafka, Firestore, Rails) and
  three duplicate folders (top-level `rules/` and `references/`, a nested `gitnexus/` copy).
  Kept Google ADK (the app's agent framework; the owner caught my mistake) and NATS
  (planned worker queue in `todo.md`). 47 → 37 entries; git history keeps the rest.
- **2026-11-01:** Owner asked for small progress updates during the sprint, "slightly more
  than currently" (preference 19): two to four lines at milestones and about every 30
  minutes when something moved, driven by a board Monitor. Updated the lead memory and the
  team-launch watchdog step.
- **2026-11-01:** Sprint 2026-10-31c closed: 19/19 pts of local-first data (039) and small
  fixes (040), plus a split QA fix round (041, 042). Cost per point 0.92 (from 0.83), in
  78 minutes from steer to wrap. Coordination rose to 38%, because the lead share includes
  meta work (skills pruning, preferences 18 and 19) and the live pass. First skills pass
  applied the sprint's learnings (developer shell facts, ADK partial events, team-launch
  notice routing). Team report: `meta/sprints/2026-10-31c/team-report.html`.
- **2026-11-01:** Retrospective on 2026-10-31c with the owner ("a bit more difficult than
  the previous one"). The work was harder (a security-core data layer plus a migration),
  and the session carried three owner meta changes mid-sprint. Friction came mostly from
  team-lead: a stale same-named PO replayed its old report, developer completion notices
  routed to team-lead again (structural, not only after a resume), a monitor quoting bug,
  the ADK pruning mistake, and one expensive live turn on a large report. Added P7
  (scoped security review at hand-off) and P8 (split lead spend by activity). Lessons in
  the lead memory and team-launch.
- **2026-11-01:** Shared knowledge vs member memories (owner's question). Decision: shared
  facts go into the agent files and skills (done at the 2026-10-31c wrap-up); team-lead
  does not edit member memories. Added a "shared before personal" line to the memory
  rules in the three agent files: cut what an agent file or skill already says, and post
  `skill:<name>` for what every agent should know. Measure at the next wrap-up: lines in
  member memories that repeat the shared files (feeds open question 3).
- **2026-11-01 (sprint 2026-11-01 wrap-up):** First tier-L run under the autonomy grant:
  33/33 pts at 1.18 M/pt, coordination 26%. P7 result and adopt recommendation recorded
  above. Shared-vs-memory measure: about 9 member-memory lines repeat the shared files
  (`env -i`, the mutation-check recipe, the Postgres image, zsh word-splitting); the
  missing ones moved into `developer.md`. Applied: `developer.md` (pgvector image recipe,
  feature.json trap, grep guard tests before a plan gate, paste the clean-run tail, mutation
  restore from a backup); `team-launch` (one-line wake-ups for the idle merger, gcloud
  pre-flight, recreate the backend after login, no `.env` symlink during suite runs).
- **2026-11-01 (after the wrap-up):** The owner adopted P7 (D18) and asked for the push.
  The scoped security review went into `product-owner.md` §3 (brief field, review steps)
  and `scrum-master.md` §4. Main pushed with the sprint.
- **2026-11-01 (board close-out):** On the owner's word, all 41 Under Review stories went
  to Done and iterations 161, 254, 266 and 290 were closed. The owner switched Team 1's
  default workflow to Standard (the MCP can't edit team settings) and handed the board to
  team-lead (D19).
- **2026-11-01 (memories):** Owner: "Please don't fiddle with team members' memories ever."
  Now owner preference 21. Team-lead had hand-edited its own `lead.md` a second time this
  sprint (board ownership, a trim to stay under the cap); that edit was reverted to the
  wrap-up version. The board grant lives in preference 20 and D19 instead.
  Owner, straight after: the lead is exempt from the once-per-sprint rule and its cap rises
  to 1000 words. `member.py` now caps per seat (lead 1000, others 500); team-launch updated.
- **2026-11-01 (board tidy, D19 in use):** Default workflow confirmed Standard. Archived the
  26 auto-generated "2025-04-DD Epic" placeholders (ids 36–61; only 37 held stories, three
  archived 2025 setup stories). Epic states now match their stories: 100, 103, 105 and 203
  in progress; 99, 104 and 248 done; the rest to do.

- **2026-11-01 (retro and session boundaries):** Sprint retro with the owner (summary in
  CURRENT.md). Practice adopted on trial: one session per sprint and separate sessions for
  meta talks, with CURRENT.md rewritten as the hand-off before each boundary. Test: does a
  fresh session repeat anything already settled? Each slip is a missing line in a file.
- **2026-11-01 (fresh meta session, tools over rules):** First fresh-session hand-off held:
  nothing settled was re-asked. The owner asked for a reflection on the team's tools, then
  for the scripts. Built P9 (above), updated `developer.md`, `product-owner.md`,
  `scrum-master.md` and `team-launch`; filed sc-336; added the prompt-size test idea to
  sc-334.
- **2026-11-01 (sprint 2026-11-01b wrap-up):** 20/20 pts at 1.03 M/pt, coordination 26%, in
  1 h 36 min from steer to wrap. First P9 trial: 0 "green that wasn't", 0 team-lead
  wake-ups (Maren used `board.py wait`), 1 of 3 merges reused a receipt, 7 messages in the
  sprint (was 40), and `lint` lines for the members who ran fell 14 → 3. The owner had the PO
  "in the room" for planning, and she corrected two of my claims from the code. Owner
  preference 23: name tickets, not bare ids. The QA High came from our own P7 rework (a lane
  move stalled the kickoff turn). Live pass 3/3. Team report:
  `meta/sprints/2026-11-01b/team-report.html`.
- **2026-11-01 (retro with the owner, after 2026-11-01b):** the owner asked how the team did,
  what was better and worse, and how I'll evolve it. Honest framing: 1.03 M/pt is cheaper than
  the tier-L sprint (1.18) but dearer than the earlier tier-M sprints (0.83, 0.92). Proposed
  P10 (lighter PO admin in tier M). Moved the liveness lesson from my memory into
  `product-owner.md` (the end-sweep prompt is hers to write, so my memory alone never
  reached it).
- **2026-11-01 (owner: "Go ahead with both, and commit it"):** measured Maren's context
  before changing anything. The lever wasn't ownership entries but Shortcut re-reads (36%)
  and report copying (10%). Built `report.py` and the shell, `usage.py --context`, and
  expected answers in `livecheck.py` (P11). Updated `product-owner.md` and team-launch.
- **2026-11-02 (sprint 2026-11-02, fully autonomous):** owner: "start and complete the sprint.
  No further interactions from me." 20/20 pts (14 stories, three streams: report fights +
  kickoff, raw-store hardening, turn + startup hardening) in 1 h 33 min; merged locally,
  not pushed. 25.3 M = 1.27 M/pt (up from 1.03), coordination 16% (lowest yet), build 68%.
  Cause, measured: Maren resumed each builder for the P7 rework and the QA fix, so later
  calls carried 210–260k context against 123k for last sprint's fresh fix agents; build per
  point 0.57 → 0.86. P10: Maren 0.134 M/pt (target ≤ 0.12, was 0.17), Shortcut 20% (target
  < 15%, was 36%), html 0% (met); new biggest slice is inline Agent results (32%). P11 first
  live use: judged prompts PASS twice; the soft kickoff miss (37.4k vs ~35k) became
  sc-367. Changes: `product-owner.md` QA-fix round in fresh agents; `developer.md` final
  result ~25 lines; `team-launch` live-check board convention; `livecheck.py` raid-only
  `--facts` + `killdiff`. Team report: `meta/sprints/2026-11-02/team-report.html`.
- **2026-11-02 (owner feedback after the sprint):** the owner found the plan, sprint review
  and team report unreadable. Cause: the report shell from P10 laid out check lists,
  callouts and cards as CSS grids, which put every word on its own line, and its class guide
  sent writers to the badge class `.no`. Fixed in the shell and guide (a2c0ce5); `report.py`
  now tells writers to screenshot each tab before sending. Also restored the sprint's QA
  reports, which `git worktree remove` had deleted (gitignored); `team-launch` copies them
  first now. Added an "Earlier sprints" tab to the team report on request. Owner: "Well
  done"; pushed on their go.
- **2026-11-04:** The owner asked for the architecture docs to match the code exactly and to
  stay current: "make sure this is written down somewhere that part of the sprint close-out
  step this architecture documentation must be updated to always reflect the current
  state". Rebuilt `documentation/architecture/` from 3 long pages into an index plus 13
  topic pages. Six parallel agents each re-checked one area line by line at `1df8f6f`; the
  old pages were 6–9 days and about 240 commits behind (no knowledge base, provider switch
  or local-first store). New close-out step: the product owner's wrap-up step 5 runs
  `.claude/team/archdocs.py changed` → re-verify → `stamp` → `check`, and team-lead gates
  the merge question on it (`team-launch` wrap-up step 4). Owner preference 24.
- **2026-11-04 (later):** Telemetry planned with the owner and Maren the same morning
  (specs/telemetry_spec.md §14, epics 395–397, 27 stories), then sprint 2026-11-04
  (Telemetry 1) ran: 23/23 pts, 1.17 M/pt, coordination 29%, 2 h 54 min. QA fixes in fresh
  agents paid off (Nils 0.81 vs 7.65 build). A file-ownership question waited 55 min because
  the PO's wait woke only on hand-offs → `product-owner.md` now arms it with questions too.
  Next sprint levers: quick mode for the stack test scripts; split 12-point security-core
  streams; measure screenshot `Read` cost (90% of the lead's new context by characters);
  provider switch in `livecheck.py`.
- **2026-11-04 (wrap-up):** On the owner's request during the live walkthrough, the team's
  history became data: `.claude/team/teamstats.py` pushes each sprint's facts (this
  baseline table, `usage.txt`, the board export) to Mimir, and Grafana's "Agent Team:
  Improvement" dashboard (D13, sc-439) shows them across all nine sprints. It runs at
  every wrap-up now (team-launch step 3). First reading: minutes per point 7.5 on 11-04 vs
  4–6 before, mostly the unwatched question; Nils's 268k context per call is the largest
  single lever. Lesson: the live pass ran on an Alloy started before the QA fix to its
  config, so identifier labels still reached Mimir; restart config-reading services
  before a live check (lead memory).
- **2026-11-05 (meta session, cost of Telemetry 2):** Owner opened with meta, as agreed, and
  asked where Telemetry 2's extra cost went. Measured as P12: build got cheaper per point;
  the extra sat in the QA fix rounds (+3.8), the new docs close-out running twice (+2.8),
  the PO (+2.4, of which 2.05 were cold-cache wakes) and the lead (+2.0, the owner's panels
  and the live pass). Screenshots are not the cost (my 11-04b guess was wrong). Three
  levers proposed; owner to decide.
