# US4 review — opportunity-based cast coaching (quickstart "US4" steps 1–4)

Automated: `backend/tests/test_cooldowns.py` (opportunity formula, spell-id/name matching,
death + intermission shrink eligible time, eligible time independent of WCL `activeTime`,
no guide ⇒ rates only, unknown-patch guide ⇒ `freshness_caveat`, player errors incl.
ambiguity, tool summary) and `test_fight_time.py` (`intermission_windows`) — **pass**.

Manual steps need the running app with ready guides in the registry (restart after
regenerating a guide, or rely on the post-generation `set_guide_meta`). Reference pulls
from `baseline.md`.

| Step | Check | Result | Notes |
|---|---|---|---|
| 1 | early-death pull (fight 17, 동주술옥 Shaman) → "N of ~M opportunities" with M over **alive** time; dead time shown | _pending_ | needs a ready Shaman guide (spec from the Casts `icon`) |
| 2 | intermission encounter (fight 47 Ula'tek, or fight 9 Nek'zali) → intermission time excluded, `excluded_windows_unknown` stated | _pending_ | |
| 3 | spec with no ready guide → rates vs cohort only; the word "missed" absent | _pending_ | |
| 4 | spec whose guide is unknown-freshness → counts labelled **approximate** with the freshness note | _pending_ | |
