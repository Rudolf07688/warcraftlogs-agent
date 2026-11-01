# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-01 (end of sprint 2026-10-31c)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D17, proposals P1–P6, baseline table, change log).

## Where we are

- **Sprint 2026-10-31c is merged and pushed** (6f31f72): 19/19 pts of local-first data.
  Team report: `meta/sprints/2026-10-31c/team-report.html`. The DB is at 0018 and the
  stack runs from main.
- **New this session:**
  - preference 18 / D17: team-lead owns the skills;
  - preference 19: small progress updates;
  - P7 (scoped security review) and P8 (split lead spend) proposed;
  - a "shared before personal" memory rule.

## Next sprint steer (owner, 2026-11-01)

Big sprint: the semantic knowledge base (epic 100). The design is agreed with the owner in
`documentation/designs/20261101_semantic_knowledge_base.md`; read it first.
- **Scope:** WCL fetches (039 sharing rule), class guides, and chats. Chats are
  workspace-scoped, like conversations today.
- **Approach:**
  - Vertex embeddings: `gemini-embedding-001` at 768 dimensions. Access checked on
    2026-11-01.
  - pgvector, with hybrid search: full-text search merged with vectors by RRF.
  - Typed metadata filters, resolved by the server.
- **Tickets, 33 pts, all in Shortlist with design notes and estimates:**
  - sc-111, sc-112, sc-113, sc-114, sc-115, sc-304, sc-305 (epic 100);
  - sc-131, sc-132, sc-295, sc-296 (epic 103).
- **Run:**
  - tier L with a scrum master and three developers, so add a `dev-c` worktree;
  - next feature number 043, Alembic head `0018_raw_store_visibility`;
  - try P7 here: a scoped `qa-security` review at hand-off for sc-111, sc-112, sc-114 and
    sc-305.
- **Owner setup:** the Postgres image changes to `pgvector/pgvector:pg17`. Run
  `bin/01_start_app.sh --build` after the merge. Team-lead backs up the database first.
- **Pass this to the PO verbatim** in the launch brief (team-launch step 1).

## Open threads

- 20 stories are Under Review (iterations 266, 290 and 161) until the owner names Done.
- Memory quality review: count memory lines that repeat the shared files at the next
  wrap-up (open question 3).

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
