# Measurements: raid-kickoff model requests (SC-002, SC-006)

Source: the per-turn log line `turn stats model=… requests=… rounds=… …` from
`backend.app.agent_runner` (`docker compose logs -f backend | grep "turn stats"`).

**Status**: the request counter (T018/T019) landed in the same change as the prompt
steering (T021/T022), and the kickoff can only be triggered from an authenticated browser
session, so the before/after runs below still need to be collected by the operator.
To get a true baseline, temporarily check out the previous `INSTRUCTION` /
`kickoff_prompt_for` wording (git stash the two prompt edits), run the kickoffs, then
restore. Target: median `requests=` down by at least one third; a one-lookup question
still reports `requests=2`.

## Before (prompt steering off)

| Report | Model | requests | rounds | notes |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |

Median requests: —

## After (prompt steering on)

| Report | Model | requests | rounds | notes |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |

Median requests: — · Drop: — %

## Single-lookup check (SC-006)

Question: "what's the kill time on boss X in report Y?" → `requests=` — (expected 2)
