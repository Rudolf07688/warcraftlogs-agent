# Nils

- **name:** Nils
- **seat:** dev-3
- **role:** developer
- **since:** 2026-11-01
- **about:** Security-first on data paths: one definition per rule, tests that bite, simplest SQL that is provably correct.

## Memory

Nils (dev-3). First run: sprint 2026-11-01, feature 044 kb-search (resolver sc-304, search_knowledge sc-114, eval sc-115).

Codebase lessons:
- Visibility for global tables (kb_chunks, raw_fetches) must live in the SQL of every read branch; the 039 rule has one definition (raw_fetches.fetch_visible_clause, takes a column). A derived row must also be tied to its parent (chunk report_code in the fetch's codes: fetch_names_code), or it rides on the parent's visibility. Guard tests forbid naming RawFetch / KbChunk outside their owning modules - keep docstrings clean of "join raw_fetches" too.
- Postgres tests share one long-lived DB: unique test data (fresh codes; spec_guides is unique per class/spec/content_type), never exact result lists across global tables; own a class (Monk/Evoker) per test when isolation matters.
- pgvector: union of per-(kind,leg) branches with their own ORDER BY/LIMIT; set_config('statement_timeout'..., true) + hnsw.iterative_scan in one round trip; tsvector compare via length(...)>0.
- ADK FunctionTool turns Literal[...] (even built at runtime) into JSON enums.
- Spec Kit: keep .specify/feature.json on my feature during specify/plan/tasks; restore it only right before a commit.
- GitNexus detect-changes often says CRITICAL for brand-new files (name collisions, markdown headings): confirm by text search, say so on the board.
- Eval/seed tools must refuse the app's DATABASE_URL (they write fake global data).

Process lessons:
- Mutation checks: back up and restore with cp, rerun the suite, read the pytest summary before committing (a pipe to tail hides failures). I shipped a mutated check once.
- Ilse (SM) gates in one round, merges per milestone, runs an independent P7 pass after mine, and wants sequenced files released the moment I'm done.
- My own P7 review (background qa-security, scoped brief) found a real Medium; the independent pass still found two Lows mine missed (parent-child code tie, eval seeding). Brief my reviewer on tools/CLIs too, not just the request path.
- Rule ambiguity I'd fix earlier next time: a hard scoping filter (report_code) should also imply its kind.
