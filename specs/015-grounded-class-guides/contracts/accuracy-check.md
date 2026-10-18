# Contract: Guide & coaching accuracy check (feature 015, Story 4)

A maintainer-run command, not part of CI's default `pytest` run (it calls live models and
Warcraft Logs). Deterministic sub-checks also run as normal unit tests.

## Command

```bash
uv run python -m backend.evals.guides run [--baseline] [--specs Mage/Fire,DemonHunter/Devourer]
                                           [--content raid,mplus] [--skip-coaching] [--live-generate]
```

- Default: scores the **currently published** guides in the DB (no generation) plus the
  coaching set → report.
- `--live-generate`: generates fresh guides for the selected specs through the full
  pipeline first (costly; used to score a pipeline change before it ships).
- `--baseline`: writes the report to `backend/evals/guides/reports/baseline.json` (committed).
  FR-024: the baseline is recorded **before** any other story is merged, against today's
  guides and coaching.
- Exit code `0` = gate passed, `1` = gate failed, `2` = run error.

```bash
uv run python -m backend.evals.guides datasheet <Class>/<Spec> <raid|mplus>   # print a data sheet (debug, quickstart §3)
```

## Inputs (`backend/evals/guides/`)

| Path | Shape |
|---|---|
| `facts/<raid|mplus>/<Class>-<Spec>.json` | `[{id, statement, expected: "present"\|"absent", match: [regex], contradict: [regex], notes}]` — ≥5 per spec, ≥3 specs incl. `DemonHunter-Devourer`, both content types (FR-021) |
| `adversarial/<case>.json` | the six cases: `old_similar_guide`, `ptr_newer_than_live`, `conflicting_guides`, `hotfix_after_publish`, `new_spec_thin_data`, `raid_question_only_mplus_brief`; each = fixture inputs + expected outcome |
| `coaching/<id>.json` | `{report_code, fight_id\|null, player, class_name, spec, content_type, question, expected_points: [{id, kind: "raise"\|"not_contradict", match: [regex], contradict: [regex]}]}` |

Facts are hand-checked by the maintainer against the live game (notes field records how).

## Scoring

| Metric (FR-023) | Definition |
|---|---|
| patch_accuracy | share of scored guides whose published patch (and season for mplus) equals live |
| claim_support_rate | confirmed claims / all claims in published guides (from stored `claims[].verdict`) |
| leakage_rate | cited sources (published `sources` + `evidence.fact_sheet.items` used by claims) whose URL/title/env tags are PTR/beta/Classic ÷ all cited |
| current_source_precision | cited sources valid for live patch (tags + date ≥ patch start) ÷ cited |
| spec_coverage | roster specs present in `GET /api/guides` ÷ roster specs (game data) |
| fact_accuracy | per fact: `correct` (present & matches, or absent & absent), `omitted` (expected present, not stated, listed in unconfirmed), `wrong` (contradict regex hit, or absent-expected stated) |
| abstention_quality | omitted ÷ (omitted + wrong) |
| source_link_health | HEAD/GET 200 within 10 s ÷ cited links (sampled ≤ 50) |
| wrong_content_brief_use | coaching runs where the brief given/fetched had the other content type ÷ coaching runs (from turn logs / tool calls) |
| coaching_point_accuracy | per expected point: `raised`, `missed`, `contradicted` |

## Release gate (FR-025, SC-002/003/008/009)

Fails when any of: `leakage_rate > 0`, `wrong_content_brief_use > 0`, `patch_accuracy < 1.0`,
`claim_support_rate < 0.95`, any fact `wrong`, any adversarial case failing, any
coaching point `contradicted`. Reports also compare against `baseline.json`
(SC-010: wrong-fact share −80%; SC-011 coaching raised ≥90% and better than baseline).

## Output

`reports/<UTC timestamp>.json` (full detail) + `.md` (summary table per spec × content type,
gate verdict, deltas vs baseline). `reports/` is gitignored except `baseline.json`.

## Unit-test counterparts (run in normal `pytest`)

Hard filters, deterministic checks, brief rendering/budget, content-type classifier, scoring
functions (on fixture guides) — so the scoring logic itself is tested without live calls.
