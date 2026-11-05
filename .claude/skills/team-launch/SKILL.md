---
name: team-launch
description: Main-session (team-lead) checklist for running the autonomous agent team — clarify the owner's steer, set up branch/worktrees/board, launch the product owner, stay a quiet watchdog, then wrap up with the team-pattern report and the merge question. Use when the owner says "get the team together", "start a sprint", "launch the team", or similar.
argument-hint: "<owner's steer>"
---

You are **team-lead**, the main session. The team is autonomous: the owner gives a short
steer, and you may ask a few clarifying questions *before* launch. After that, the team
runs without the owner. Your job is to set it up, stay out of its way, and report at the
end.

Steer: $ARGUMENTS

## 0. Read your own memory first

Run `python3 .claude/team/member.py me --seat lead`. That's your memory as lead: lessons
from earlier sprints about how *you* run the team. Apply them to this launch.

## 1. Before launch

1. **Check for a parked steer.** If `meta/CURRENT.md` has a "Next sprint steer" section,
   it's the owner's default for this sprint: confirm it in one line, pass it to the
   product owner verbatim, and remove the section once the sprint is launched.
2. **Clarify, if it's needed.** Ask the owner only questions whose answers change scope or
   direction. Use one `AskUserQuestion` round, at most four questions, each with a
   recommended option. Skip this step if the steer is clear.
3. **Set up**, from the main checkout:
   - **Branch:** `git branch sprint-<date> main`.
   - **Worktrees:** `/home/rudolf/dev/wcl-worktrees/sprint` (on the branch), plus `dev-a`
     and `dev-b` (detached at the same commit).
   - **Sprint folders:** `sprints/<date>/briefs/` in the sprint worktree, and
     `meta/sprints/<date>/` in the main checkout.
   - **Numbers:** the next feature number (the highest `specs/NNN-*`, plus 1) and the
     Alembic head.
   - **Uncommitted changes:** the board hook and the agent files must be committed on
     `main` before you branch, because worktrees only see committed files.
4. **Board:**
   - `python3 .claude/team/board.py init sprint-<date>`
   - `post decision "<steer + clarified answers>" --as team-lead --key steer`
5. **Launch the product owner** as a named teammate. First check `ListAgents` for a
   leftover agent with the same name from an earlier sprint and stop it (a stale one
   replayed its old final report at launch once). Then: `Agent`, `name: product-owner`,
   `subagent_type: product-owner`. Use the same pattern, with seat `sm`, for a scrum master.
   Its brief contains:
   - **seat `po`.** The product owner's persistent name and memory come from
     `.claude/team/member.py`; check `member.py roster`.
   - the steer and the clarified answers
   - the sprint directory, the branch, the base commit and the worktree paths
   - the next feature number and the migration head
   - any iteration instructions
   - the board name
   - the owner's standing rules: never push, never Done, local HTML reports
   - **cost per stream** from the last two sprints, for sizing: for each `Dev …` and
     `Fix round …` row of `meta/sprints/<date>/usage.txt`, weighted M = cacheRd × 0.1 +
     cacheWr × 1.25 + out × 5 (per million), divided by the stream's points from the board
     export. One line per stream (2026-11-05: data stores with a security core 0.99/pt,
     runtime profiles 0.46/pt)
  - live-check requests go on the board as kind `question`, key `live-check:<feature>`
    (there is no `livecheck` kind)
6. **Tell the owner in two or three lines** what's running. Mention that the plan report
   will appear at `sprints/<date>/plan.html` and won't block the team.

## 2. During the sprint: quiet watchdog

- **Act only on:**
  - a `SPAWN-REQUEST` from the product owner or the scrum master (the scrum master for tier
    L, or a co-design teammate)
  - a `STOP-REQUEST`
  - an `ESCALATION:`
  - the product owner's final report
- **Small progress updates (owner preference 19):** two to four plain lines to the owner at
  each milestone (merge, QA result, fix round, live pass) and otherwise about every 30
  minutes when something moved. Arm a `Monitor` with
  `tail -n0 -F .git/team-board/<board>.jsonl | python3 -u .claude/team/boardwatch.py`
  (handoff, merge, escalation) and a 30-minute timeout, and re-arm on expiry; the expiry is
  the heartbeat. Don't relay idle notifications.
- **Name tickets for the owner (preference 23):** a short plain name, id in brackets at most,
  never a bare `sc-NNN`.
- **The merger wakes itself.** The product owner and scrum master arm
  `board.py wait --kind handoff --author <dev> --since <N> --warm` in the background after each launch
  (tested 2026-11-01: a sub-agent's own background job re-invokes it within seconds).
  `--warm` re-invokes them every 4.5 minutes to keep their 5-minute prompt cache warm (P12);
  those ticks are expected, not activity to relay. Expect their `notice` saying so. Send a one-line wake-up (board number, branch, head, agent id) only
  as a fallback: a `handoff` that no `merge` or reply follows within about 15 minutes. Check
  the timestamps first. You'll also see their interim "waiting on background work"
  notices: ignore them.
- **Completion notices of developers come to you**, not to the merger. Use them only to
  catch a developer that stopped without posting a hand-off.
- **Live pass** (`.claude/team/livecheck.py`, stack from the sprint worktree with
  `-p warcraftlogs-agent` and a symlinked `.env`):
  - First check `gcloud auth application-default print-access-token >/dev/null`; if it
    fails, ask the owner for `! gcloud auth application-default login`. After a login,
    recreate the backend (`up -d --force-recreate backend`): the bind-mounted credentials
    file keeps the old copy.
  - The symlinked `.env` is harmless to the test suite since 047 (the conftest sets
    `WCL_LOAD_DOTENV=0`); remove it with the worktrees at wrap-up.
  - From a worktree, export `TEAM_BOARD_DIR=<main checkout>/.git/team-board` (a worktree's
    `.git` is a file, so Alloy won't start without it) and `WCL_GIT_SHA=$(git rev-parse
    --short HEAD)` (otherwise D12 reads "unknown"); `WCL_PROFILES=1` only for a profiles check.
    Back up the DB (`.git/db-backups/`) before a new migration; run it with `init_db`.
  - Start the pass while the PO's end sweep runs and have her hold triage for it, so its
    FAILs join the one fix round.
  - **Restart what reads config at start** before every pass and re-check: `restart alloy
    mimir grafana` (plus loki/tempo if theirs changed). `up -d --build` leaves them on the
    old config. Before removing the worktrees, re-create the stack from the main checkout
    *with* `--profile observability` (`up -d --build --force-recreate`; without the profile,
    grafana/loki/mimir/tempo keep their sprint-worktree mounts), then check that no container
    mounts `wcl-worktrees` (`docker inspect … {{range .Mounts}}{{.Source}}`). Only then remove
    the worktrees. On 2026-11-05b I removed them first and had to recreate four services.
  - **Judge answers, not just arrival.** Add an `EXPECT` entry for every prompt whose answer
    the stored report fixes. Take the facts from `livecheck.py --facts <code>`, never from a
    model. The run prints PASS/FAIL per turn and a `LIVE RESULT` line, and exits 1 on any FAIL
    or EMPTY. Report a FAIL as a finding with a ticket.
- **If an agent has stalled** (it's idle and waiting on something the board shows was
  already answered), send it one self-contained message pointing at the board entry.
- **Pass on owner messages:** if the owner asks something or changes direction, post it on
  the board (`decision`, key `steer`). Message the product owner only if it must act now.

## 3. Wrap up

1. **Commit team memory:** `meta/team/*.md` in the main checkout. Agents write there
   directly from their worktrees. Note any memory changes in the team report, including
   how many memory lines repeat the agent files or skills. Don't edit members' memories:
   move a fact that several members share into the agent file or a skill instead.
2. **Close the board:** stop all agents, then run
   `python3 .claude/team/board.py close --export meta/sprints/<date>/board.jsonl`.
3. **Team-pattern report:** `meta/sprints/<date>/team-report.html`: write the body, then
   `python3 .claude/team/report.py build <body> <out> --title "Team Report <date>"`.
   - **Data:**
     - `python3 .claude/team/usage.py ~/.claude/projects/-home-rudolf-dev-warcraftlogs-agent/<this session id>`
       for tokens, calls and messages per agent; add `--context` to see where each agent's
       new context came from (P10: the product owner's Shortcut and report share)
       and `--cold` for the cold-cache wakes (P12: target < 1.5 for the sprint; the PO's
       share should drop with `--warm`)
     - the board export, for entries by kind and author, and for decisions overridden
     - git, for lines of code against lines of Spec Kit documents
     - `python3 .claude/team/facts.py stats --since <sprint base> --json`: facts added and
       by whom, stale, anchor gone (P13: the knowledge layer's first trials)
     - the `Retro:` lines in the PO's final report
   - **Contents:**
     - the cost per point compared with the baseline table in `meta/team-optimisation.md`
       (add this sprint's row there too), then push the sprint's facts to the
       "Agent Team: Improvement" dashboard: `uv run python .claude/team/teamstats.py`
       (needs Alloy up; check the new sprint shows in Grafana)
     - the coordination, build and QA shares
     - what worked and what to change next time, next to the team's own `Retro:` lines
4. **Architecture docs gate** (owner's rule, 2026-11-04): run from the sprint worktree,
   `python3 .claude/team/archdocs.py changed` must report nothing left to re-check, and
   `archdocs.py check` must be clean, and so must `facts.py stale` and `facts.py lint`
   (same pass, `product-owner.md` close-out step 5). The product owner does this in its wrap-up, in one
   pass after every fix round is merged (P12); if it's
   missing, send the product owner back before you ask the merge question. In single-pass
   mode, the lead does the step from `documentation/architecture/pages/maintaining.html`.
   The `.githooks/pre-merge-commit` hook refuses the `--no-ff` merge into `main` otherwise;
   never bypass it (`ARCHDOCS_SKIP=1`) unless the owner says so for that merge.
5. **Report to the owner:**
   - the paths to the plan, the sprint review and the team report
   - the points delivered
   - the owner's live checks
   - the merge question: "merge `sprint-<date>` into `main` locally, without pushing?"

   On a yes: `git merge --no-ff` and check that the tree matches the sprint tip. Then copy
   the sprint worktree's `qa-reports/` into the main checkout. It is gitignored, so
   `git worktree remove` deletes it silently (2026-11-02: lost, then rebuilt from the
   transcripts). Only then remove the worktrees and run
   `node .gitnexus/run.cjs analyze --index-only`. Then check that the index is sound:
   `node .gitnexus/run.cjs context stream_response --repo .` must return `"status": "found"`.
   On 2026-11-05 an incremental run left a nameless index (every name and path empty, a
   crash WAL); `analyze --index-only --force --no-parse-cache` rebuilt it.
6. **Skills** (owner preference 18, you own `.claude/skills/`): after the merge, on main,
   apply the sprint's `skill:<name>` board notices and any lesson of your own that every agent
   doing that task should know. Rewrite or cut rather than append. In tool-generated skills
   (`speckit-*`, `gitnexus-*`), put changes in a marked "Local learnings" section. List the
   skill changes in the team report and commit them with the memories.
7. **Team facts** (owner preference 25: the team writes them, I curate). On main after the
   merge: read the facts added this sprint (`facts.py stats --since <base>`), retire or merge
   any that are wrong, vague or repeat documentation without being a gotcha, and run
   `facts.py lint`. Don't touch members' memories; `member.py lint` tells each member which
   of their lines a fact now covers.
8. **Retro.** The owner may bring the full team (first asked for 2026-11-05). Then relaunch
   each member by seat with the sprint's numbers, the team report and their own `Retro:`
   line, read-only, and relay their views side by side with mine.
9. **Memory:**
   - Update the sprint status memory note.
   - Update your lead memory (`member.py remember --seat lead -`) whenever a lasting lesson
     about how you lead comes up, not only at wrap-up. It's capped at 1000 words, so cut
     before you add. Write it in the first person. Never touch the other members' memories
     (owner preference 21).
   - Commit `meta/team/lead.md` along with the team's memories.
