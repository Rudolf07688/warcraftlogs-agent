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
