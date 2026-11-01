# Scrum master brief: sprint 2026-11-01 (semantic knowledge base)

From Maren (PO). Seat `sm` (new seat: claim your own name first).

## Read first
- `sprints/2026-11-01/plan.md`: features, stories, ACs (copy them verbatim into dev briefs), order, risks.
- `documentation/designs/20261101_semantic_knowledge_base.md`: the agreed design.
- Board: `python3 .claude/team/board.py current`. My decisions #2-#9 (features, order, tiers, staffing, hot spots, drop order).
- `.claude/agents/scrum-master.md`, `product-owner.md` §3, `developer.md`.

## Setup
- Sprint branch `sprint-2026-11-01`, worktree `/home/rudolf/dev/wcl-worktrees/sprint`, base `ec966c5`.
- Dev worktrees (detached at ec966c5): `/home/rudolf/dev/wcl-worktrees/dev-a` (043), `dev-b` (044), `dev-c` (045).
- Seats: dev-1 Ansel -> 043, dev-3 (new) -> 044, dev-2 Tomas -> 045. Model recommendations in board #7; you post the final `model:<NNN>`.
- **Spawning:** team-lead asked that developer spawns go through them: send team-lead `SPAWN-REQUEST seat/model/effort/brief-path` per developer (all three in one message is fine). Write briefs to `sprints/2026-11-01/briefs/<NNN>-<name>.md`.
- Migration: `0019_kb_chunks`, `down_revision = "0018_raw_store_visibility"`, 043 only. Lockfile (`pgvector`) and `docker-compose.yml` to 043 only.

## What I need from you
1. **Milestone merges first:** sc-304 (044) and sc-111 (043) merge into the sprint branch as early as possible; the other streams rebase on them. Per-story merges are fine where someone waits.
2. **File ownership:** sequence the hot spots (board #8): `wcl_agent/agent.py` (044 + 045), `backend/app/services/fetch_persistence.py` (043 hook + 045 writer), the chat-turn persistence path (043 sc-305 + 045 sc-132).
3. **P7 (owner's trial):** at hand-off of sc-111, sc-112, sc-305 (043) and sc-114 (044), run a scoped `qa-security` agent on that branch's diff before merging, plus the bypass attempts: a chunk whose fetch is no longer visible, another workspace's chat chunk, crafted filters that widen scope, a deleted conversation. Fix criticals before merge (counts as the one rework round). Note the findings and cost on the board (key `p7:<NNN>`) so the team can judge P7.
4. **Merge checks** (product-owner.md §3): footprint, rebase, `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q` on the rebased result, Postgres-only tests on a throwaway `pgvector/pgvector:pg17` container (never the compose db; remove it afterwards, disk is tight), GitNexus analyze + detect-changes, `--no-ff`, post `merge`. Never push, never merge to main.
5. **Tickets:** devs move their stories to In Progress at start and Under Review at hand-off. I set the iteration (Q4, id 161) on all 11 now.
6. **Gates:** 043 and 044 gate after spec and after plan (with file list); 045 after plan only. One round per gate. Product questions to me as a board `question`.
7. Developers record clarify answers on the board. The drop order (board #9) applies if we run late; ask me before dropping.
8. When all three are merged: post `handoff` to me and send me one message. I run the QA sweep and the wrap-up.

## Practical notes (from earlier sprints)
- Agent shells carry live app env vars: always run suites under `env -i HOME=$HOME PATH=$PATH`.
- zsh doesn't word-split a command stored in a variable; use a shell function.
- The frontend build dirties `frontend/tsconfig.tsbuildinfo`; check it out before merging.
- A dev resumed with SendMessage returns immediately; wait for its board hand-off.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
