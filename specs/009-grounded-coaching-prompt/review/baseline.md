# Baseline (before any code change) — feature 009

Recorded 2026-10-07 on branch `009-grounded-coaching-prompt` at commit `d03c436`
(the last commit before this feature's code changes).

## T001 — test suite on unchanged code

Command: `uv run --extra test pytest -q` (equivalent to `pytest backend/tests`; the
untracked local `google-cloud-cli-linux-x86_64/` download broke collection, so
`testpaths = ["backend/tests"]` was added to `pyproject.toml` and the download was
gitignored before the first code task).

| Result | Count |
|---|---|
| passed | 236 |
| skipped | 3 |
| failed | 0 |

## T002 — reference pulls (quickstart Prereqs)

All from report `cFHpyKdLWAajwZCM` (The Venomous Abyss, zone 53; a Korean guild on
server 아즈샤라). Probed live on 2026-10-07 via the Deaths table and `phases`.

| Role in review | Report | Fight | Encounter | Difficulty | Result | Duration | Player | Notes |
|---|---|---|---|---|---|---|---|---|
| Kill (clean) | cFHpyKdLWAajwZCM | 9 | Nek'zali the Soulcoiler (3470) | Heroic | kill | 264 s | **Hrslkks** (Mage, source 7) | did not die; 3 phase transitions |
| Wipe | cFHpyKdLWAajwZCM | 45 | Ula'tek (3492) | Heroic | wipe @ 56% | 276 s | Hrslkks (Mage, source 7) | 2 transitions |
| Early death in a kill | cFHpyKdLWAajwZCM | 17 | Entombed Sentinels (3445) | Heroic | kill | 293 s | **동주술옥** (Shaman, source 21) | died at 33 s (11% of the fight); only death on the pull |
| Intermission encounter | cFHpyKdLWAajwZCM | 47 | Ula'tek (3492) | Heroic | kill | 588 s | Hrslkks (Mage, source 7) | encounter has "Intermission: The Shattering"; 4 transitions; Hrslkks died at 582 s (99%) |

Also useful: fight 9 has a mid-fight death (동주술옥 at 124 s, 47%) and three deaths
in the last 25 s; encounters 3470, 3429, 3445 and 3492 all define intermission phases.

Duplicate-name case: none in this report (all 30 players are distinct). The
`test_fight_time.py` unit test covers it (quickstart US2 step 6).

## T002 — the 10 baseline coaching questions (SC-011 / SC-012)

Ask each against the **unchanged** prompt (commit `d03c436`) and again on this
branch at the end (T044). Record wall-clock seconds and paste the answer.

| # | Question | Baseline answer | Baseline s | Branch answer | Branch s |
|---|---|---|---|---|---|
| 1 | Why was Hrslkks's parse low on report cFHpyKdLWAajwZCM fight 9? | _pending_ | | | |
| 2 | How does Hrslkks compare to similar Fire/Frost Mages on cFHpyKdLWAajwZCM fight 9? | _pending_ | | | |
| 3 | What killed us on cFHpyKdLWAajwZCM fight 45? | _pending_ | | | |
| 4 | Was 동주술옥 standing in the wrong place on cFHpyKdLWAajwZCM fight 17? | _pending_ | | | |
| 5 | Did 동주술옥 use their major cooldowns well on cFHpyKdLWAajwZCM fight 17? | _pending_ | | | |
| 6 | What did Hrslkks parse on cFHpyKdLWAajwZCM fight 47, and what does that mean? | _pending_ | | | |
| 7 | How are Fire Mages doing on Nek'zali heroic? | _pending_ | | | |
| 8 | What does the #1 Mage on Nek'zali heroic do differently from Hrslkks on fight 9? | _pending_ | | | |
| 9 | Did anyone die to an avoidable mechanic on cFHpyKdLWAajwZCM fight 47? | _pending_ | | | |
| 10 | Give me the top 3 things Hrslkks should fix based on cFHpyKdLWAajwZCM fight 9. | _pending_ | | | |

**Status**: pulls and questions recorded. The baseline *answers* need the running app
(Vertex + WCL credentials) and were not captured in the automated run — capture them
from the `main` build (or `git stash` the branch) before comparing in T044.
