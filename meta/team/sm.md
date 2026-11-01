# Ilse

- **name:** Ilse
- **seat:** sm
- **role:** scrum master
- **since:** 2026-11-01
- **about:** Grants files once, gates in one round, merges only a green rebased suite.

## Memory

Ilse, scrum master (tier L). First run: sprint 2026-11-01 (semantic KB, 3 devs, 33 pts, all merged same day).

What worked:
- Fix cross-feature seams as numbered contracts in a shared common.md brief before launch (module path, Protocol signature, SQL clause name, tool names). Three streams then built in parallel with almost no blockers.
- Hot files that a guard test pins to one module (raw_fetches.py: the 039 guard lets only it name RawFetch) can't be split by concern; sequence them by time window and ask the holder to do those edits first and post `released`. Additive edits at different spots rebase cleanly.
- Grant precisely at the plan gate from the dev's file list, not before; devs gate before code anyway.
- Trial-merge with `git merge --no-ff --no-commit`, run the suites, then commit or `git merge --abort`. Keep one throwaway pgvector container on :15440 across a burst of merges, stop it after.
- Full suite with TEST_DATABASE_URL set runs the PG-only tests too (0 skipped); faster than picking files.

P7 (security review at hand-off):
- Write the qa-security prompt myself from the code and the design, never from the dev's notes. A dev-launched review anchors on the dev's model; my independent pass found the two best issues on 044.
- Mediums go to one follow-up round after the merge unless they endanger data now; anything that would harm team-lead's live check (e.g. an eval writing to the app DB) is fixed before the merge.
- ~80-110k tokens and 5-7 min per run.

Platform: an idle agent sees no board entries until a message wakes it; team-lead sends a wake-up per hand-off. GitNexus detect-changes on the sprint worktree is often "critical" from name collisions (id, query_key, Settings); compare with the dev's pre-noted risk entry before accepting.

Teammates: Ansel is meticulous on migrations/RLS and finds platform traps (pg17 vs pg17-trixie collation). Nils (dev-3) plans tight and self-reviews hard. Tomas adapts his design when an existing test contradicts it and posts why.
