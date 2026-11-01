# QA fix round, common rules (sprint 2026-11-01)

From Maren (PO, `maren`). Tier S: short plan, then implement. No Spec Kit. One round only.

- QA sweep reports: `/home/rudolf/dev/wcl-worktrees/sprint/qa-reports/2026-11-01-1258/` (bugs.md, security.md, performance.md, spec-conformance.md; gitignored, read them there).
- **Base ref:** the sprint tip `sprint-2026-11-01` (7bfc119). In your worktree: `git switch -c qa-fix-<name> sprint-2026-11-01` (your old feature branch is merged; don't reuse it).
- **Footprint:** only the files listed in your brief, plus new or existing test files for them. Anything else: return "blocked: ..." with the reason.
- **Fix only the listed findings.** Each gets a regression test that fails without the fix (mutation-check it; restore from a cp backup, not git checkout; never `pytest | tail && git commit`).
- Suite: `env -i HOME=$HOME PATH=$PATH uv run --extra test pytest -q`. If you touch Postgres-only paths, run them on your own throwaway `pgvector/pgvector:pg17-trixie` container on a spare port, check the port is free first, and remove the container after. Never the compose database.
- GitNexus: impact before editing a symbol; `node /home/rudolf/dev/warcraftlogs-agent/.gitnexus/run.cjs detect-changes --scope all --repo .` before committing.
- Commits end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Never push.
- Don't touch tickets; I handle the board. Post your hand-off on the board (`handoff`, key `status:qa-fix-<name>`) and return: branch, commits, files, test counts, finding -> test mapping.
- Three of you run in parallel on disjoint files: Ansel (043 code), Nils (044 code), Tomas (cache layer).
