# Meta: current focus

<!-- Working memory for meta discussions. The SessionStart hook injects this file after a
compaction, a resume or a new session while Status is "active". Keep it under about 40
lines, and rewrite it (don't append) at the end of every meta exchange. -->

Status: active
Updated: 2026-11-05 evening (retro done, knowledge layer built; main pushed 7aadd21)

## Topic

The agent-team redesign: persistence and autonomy. Full record in
`meta/team-optimisation.md` (decisions D1–D20, proposals P1–P13, baseline, change log).

## Where we are

- Telemetry 3 merged to main 6b1a465. **Owner ended the telemetry epic** in the retro.
  Stories Under Review (Done is the owner's). Main pushed by the owner's word (7aadd21).
- Retro → **P13 / D20, owner go: team knowledge layer, built and committed.**
  `.claude/team/facts.py` plus 66 facts in `.claude/team/facts/`, anchored to symbols, files
  and components. They surface in briefs (`facts.py brief`), on demand (`for`) and at every
  commit (pre-commit hook). `stale`/`verify` run at close-out. Agents write facts directly
  (owner preference 25); I curate. Also `jobwait.py` (warm waits on developers' long jobs),
  cost per stream in the PO's sizing, and a `Retro:` line in every hand-off. All of it is
  wired into developer/PO/SM.md and team-launch.
- GitNexus on main was rebuilt with `--force --no-parse-cache` after an incremental run left
  a nameless index. team-launch now checks a known symbol after each analyze.

## REMIND THE OWNER

- **The next retro has the full team** (owner, 2026-11-05): raise it when the next sprint's
  PO report lands. team-launch wrap-up step 8 says how.

## Sprint 2026-11-05b (running, first trial of P13)

- Launched 17:48Z, board sprint-2026-11-05b, branch from 0678ea7. Owner confirmed my proposal: back to the app.
  Semantic search always down (sc-428; lead: the 3 s embed budget), D8 misses cancelled
  embeddings (sc-503), service-graph average (sc-504), dashboard ratio guards (sc-508, 1 pt),
  and as candidates: 23k prompt tokens per chat (sc-367), chat input locked after a drop
  (sc-376).
- Check at wrap-up: facts added, refused as duplicates, stale (`facts.py stats --since
  <base>`); developers' cold weight (`usage.py --cold`, target < 1.5); stack and navigation
  calls per point (scratch nav.py idea → fold into usage.py if it proves useful).
- Members' memories still hold lines that facts now cover; `member.py lint` shows each
  member theirs (23 lines). They trim them themselves.

## Open with the owner

1. Wipe the pre-fix Mimir series? (local only)
2. Gemini Flash list price changes 2027-01-01 (pricing.yaml commit that day).

Set aside (owner, 2026-11-05): long-lived Google credentials. The owner signs in when
needed (ADC lasts about 24 h); keep the pre-flight token check and ask for
`! gcloud auth application-default login` when it fails.

## How to resume

1. Read `meta/README.md`, then this file, then the latest "Decisions" and "Change log"
   entries in `meta/team-optimisation.md`.
2. Owner preferences: `meta/owner-preferences.md`.
