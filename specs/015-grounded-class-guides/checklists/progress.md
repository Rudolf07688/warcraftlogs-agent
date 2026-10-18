# Feature 015 — implementation progress and manual checks

Results of the manual / live tasks (T023, T037, T076, T110–T112). Newest first.

## QA sweep (2026-10-18)

`qa-reports/2026-10-18-1850/` found 58 findings (1 Critical, 8 High, 23 Medium, 26 Low). The top
20 % (12 findings, every Critical/High plus SEC-001/BUG-009/BUG-008) are fixed; see that
README's "Fixes applied" table. The rest are open (next: BUG-005, BUG-006, BUG-007,
SEC-002, SEC-003/SPEC-005).

## Polish (2026-10-18)

- T107 docs: README feature-015 section, `documentation/ai_guide.md` §20, `.env.example`.
- T108: one `guide run class=… outcome=… rounds=… duration_s=…` INFO line per run.
- T109: backend 754 passed / 3 skipped; `npm run build` passes (no lint script exists).
- Adversarial cases against current code: 6/6 pass (they all failed on `main`).
- **Open**: T110 release gate and T111 live walkthrough need live models (re-auth with
  `gcloud auth application-default login`) and the real database; T112 terms review;
  T113 `detect-changes` ran (49 files, risk CRITICAL — the index is stale: it still lists
  the deleted `_run_spec_guide`), so re-run `node .gitnexus/run.cjs analyze --index-only`
  and `detect-changes --scope all` before committing. Nothing is committed yet.

## T023 — how to record the baseline (FR-024: behaviour BEFORE this feature)

The working tree already contains feature behaviour, so record the baseline from `main`
with only the accuracy-check package copied in (the harness degrades gracefully where
feature code is missing — verified 2026-10-18 on a throwaway database):

```bash
git worktree add ../wcl-baseline main
cp -r backend/evals ../wcl-baseline/backend/ && cp .env ../wcl-baseline/
cd ../wcl-baseline
# point DATABASE_URL at the database holding today's guides (schema 0010 or 0011 both work)
uv run python -m backend.evals.guides run --baseline        # needs live models + WCL
cp backend/evals/guides/reports/baseline.json ../warcraftlogs-agent/backend/evals/guides/reports/
cd ../warcraftlogs-agent && git worktree remove ../wcl-baseline
```

Before that, hand-check every fact and coaching point marked `UNVERIFIED` in
`backend/evals/guides/{facts,coaching}/` against the live game, edit them, and replace the
`notes` with how each was checked. Then commit `reports/baseline.json`.

## T037 — US1 live check (2026-10-18)

- Unit and pipeline tests: green (`test_prompt_contract`, `test_guide_pipeline_briefing`,
  `test_guide_pipeline_run`, full suite 641 passed).
- Live run `run --live-generate --specs Mage/Fire --content raid --skip-coaching` against a
  throwaway Postgres (migration 0011 applied):
  - Briefing sources worked live: Blizzard version endpoint (12.1.5.70448), the news listing
    and the newest hotfix article, Warcraft Logs zones.
  - The model call failed with `RefreshError: Reauthentication is needed` (expired Google
    application-default credentials). The run correctly ended `failed / model_error` with
    nothing published.
  - **Blocked**: re-run after `gcloud auth application-default login`. The patch-accuracy
    delta vs baseline cannot be recorded until the baseline (T023) exists.

## US6 — live data sheets (2026-10-18)

`python -m backend.evals.guides datasheet Mage/Fire raid|mplus` against live Warcraft Logs:
20-player cohorts, `sufficient=True`, real ability ids (Combustion 190319, Meteor 153561,
Counterspell 2139…), M+ shortest Combustion gap 60 s (cooldown reduction), stat medians,
top builds by hash. Hand-check of 3 abilities against WCL is still open (quickstart §3).

Finding fixed on the way: the whole-raid Casts table lists only each player's top few
abilities, so major cooldowns were missing. The data sheet and `get_cooldown_usage` now
read the player's own (cached) Casts table.
**Follow-up (out of scope)**: `compare_player_to_cohort` still reduces whole-raid tables, so
its per-ability rates can miss cooldowns too.

## T076 — US5 UI check (2026-10-18)

- `npm run build` (includes `tsc -b`): passes. The frontend has no `lint` script or ESLint
  config, so there is no lint step to run.
- shadcn: `@shadcn/tooltip` added through the MCP add command. The CLI resolved the `utils`
  alias as an npm package (`cn@0.5.0`): that dependency was removed and the import fixed to
  `../../lib/utils`, like the other ui components. Audit checklist: imports, deps, types OK.
- **Open (manual)**: desktop 3-column and 360 px (no horizontal scroll), keyboard-only
  (toolbar → switch → cards → dot → actions), screen-reader labels on the switch and the
  other-type dot, SC-014 timing (find + open a spec's Mythic+ guide < 30 s).
