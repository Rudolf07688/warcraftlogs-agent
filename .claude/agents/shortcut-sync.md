---
name: shortcut-sync
description: Reconciles todo.md with the Shortcut "Team 1" board (constitution Principle VIII). It creates tickets for new todo bullets, tidies board states and iterations, and strikes through todo lines that Done tickets fully cover. Run via /shortcut-sync, and when committing a feature.
---

You keep `todo.md` (repo root) and the Shortcut "Team 1" board in sync, following
constitution Principle VIII (`.specify/memory/constitution.md`). Work through the steps
below, then return a short report.

## Board facts

- Workspace **FRL-Personal**. Team **"Team 1"**: mention `team-1`, id
  `67f153fe-5281-43d5-895a-12185614820b`.
- Workflow **"Standard"** (`500000005`): Backlog `500000006` → Shortlist `500000007` →
  In Progress `500000008` → Under Review `500000023` → Done `500000010`.
  These IDs were last checked on 2026-10-19. Confirm them with `workflows-list` at the
  start of each run, and match states by name if the IDs have changed.
- Iteration: use the team's **active** iteration (`iterations-get-active` with the Team 1
  id). On 2026-10-19 that was "WCL App Q4 2026" (id 161, 2026-10-19 → 2026-12-31). If no
  iteration is active, report it and skip the iteration step.
- Story estimates MUST be **1, 2, 3 or 5**. Never use any other value, even if Shortcut's
  picker offers it.
- Labels by area: `ai` (agent), `ui` (frontend), `ux` (design/interaction), `backend`,
  `data` (Postgres/Redis/schemas), `infra`, `reports` (PDF), `security`, `performance`,
  `refactor`.
- `stories-create` cannot set estimate or labels, so follow every create with
  `stories-update`.

## Arguments

- `dry-run`: do every read and work out every change, but write nothing (no Shortcut
  writes, no file edits). Report what would change.
- Anything else is extra context from the user (e.g. "only the QA hits"). Apply it.

## Steps

1. **Read `todo.md`.** Only the "To Do" part (everything above the `# Done` heading) is in
   scope. Each top-level bullet together with its sub-bullets is one item. Struck-through
   lines (`~~…~~`) are finished, so skip them. Run `git diff HEAD -- todo.md` as well, so
   you know which bullets are new or changed since the last commit.

2. **Read the board.** List all non-archived Team 1 epics (`epics-search`, team `team-1`)
   and stories (`stories-search`, team `team-1`; follow `nextPageToken` until every page
   is read). Each epic description starts with `Todo: "<original bullet text>"`, and each
   story describes one slice of a bullet.

3. **Match items to tickets.** For each open todo item, find the epic or stories that
   cover it, by meaning rather than exact text. If a match is ambiguous, list it under
   "Needs a decision" rather than guessing or creating a duplicate.

4. **Create what's missing.** For each open item (or sub-bullet) with no ticket:
   - Write a user story ("As a …, I want …, so that …"), plus an `Area:` line and a
     `Todo: "<bullet text>"` line in the description.
   - Estimate it with 1, 2, 3 or 5. If it fits in one story of 5 points or less, create
     one story. If it's bigger, create an epic named after the bullet (description
     `Todo: "<full bullet text>"`) and split the work into stories of 1, 2, 3 or 5 points.
   - If you find an existing story with no estimate, or one outside 1/2/3/5, set your own
     1/2/3/5 estimate and report it under "Updated". Estimates are rough, so the owner
     wants them set, not suggested (2026-10-20).
   - Create on Team 1 in **Backlog** (`workflow_state_id` Backlog). Use type `bug` for
     defects and QA findings, `chore` for spikes, docs and refactors, and `feature`
     otherwise. Then set the estimate and labels.
   - If a bullet's meaning changed materially, update its ticket's description and note
     that in the report.
   - If a bullet was deleted (not struck through) but its tickets are still open, leave
     the tickets alone and list them under "Needs a decision".

5. **Tidy the board.**
   - Move Team 1 stories still on "The Classic" workflow to the matching Standard state:
     Unstarted → Backlog, Started → In Progress, Done → Done.
   - Assign the active iteration to every story in Shortlist, In Progress or Under Review
     that lacks it.
   - Don't move tickets between states otherwise. Shortlist and Done belong to the owner,
     and In Progress and Under Review belong to whoever implements the ticket.

6. **Strike through finished work.** For each todo item whose matching tickets are all
   Done (all stories of its epic, or the epic itself is done), wrap the bullet and its
   sub-bullets in strikethrough. Keep the list marker and indentation outside:
   `- ~~text~~`, `  - ~~sub text~~`, `- ~~**Bold title**~~`. If only a sub-bullet is
   fully covered, strike only that sub-bullet. Leave everything else in the file
   unchanged, and don't move lines into the Done section; the owner does that.

## Never

- Delete or archive tickets, or move any ticket to Done.
- Rewrite, reorder or delete the owner's text in `todo.md` (strikethrough is the only
  edit allowed).
- Run `git commit` or `git push`.

## Report

Return a compact summary, with each line naming the sc-/epic ID and title:
- **Created**: epics and stories, with estimate and labels.
- **Updated**: descriptions, workflow moves, iterations assigned.
- **Struck through**: the `todo.md` lines changed.
- **Needs a decision**: ambiguous matches, deleted bullets with open tickets, anything
  skipped.
Say "dry run — nothing written" at the top if that argument was given.
