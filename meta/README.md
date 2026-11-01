# meta

Notes and documents about **how we work**: the agent team, its setup, process and
tooling. Nothing in here is about the WCL app itself; project work lives in
`documentation/`, `specs/` and `sprints/`.

| Path | What it holds |
|---|---|
| `CURRENT.md` | **Working memory**: the current meta topic, where we left off, and open threads. Rewritten at the end of every meta exchange. |
| `team-optimisation.md` | The full record of the agent-team redesign: evidence, decisions, proposals, change log |
| `owner-preferences.md` | The canonical list of the owner's process preferences |
| `sessions.md` | A ledger of session ids, so raw transcripts can be found while they still exist |
| `sprints/<date>/` | Per-sprint team data: `usage.txt` (token and message numbers), `board.jsonl` (the exported team board), `team-report.html` |
| `team/` | The persistent team members: one file per seat, with a self-chosen name and a memory capped at 500 words (the lead seat: 1000). Written by the agents through `.claude/team/member.py`. |
| `agent-team/` | The owner's original team prompt and the first role notes (`team-00-*`) |

Agent-facing helpers live in `.claude/team/`: `board.py` (incl. `wait`), `member.py` (incl. `lint`), `check.py` (clean suite runs with receipts), `pg.py` (throwaway Postgres), `mutate.py` (mutation checks), `guards.py` (architecture guard tests), `livecheck.py`, `boardwatch.py`, `usage.py` and `meta_context.py`.

## How meta knowledge survives

| Layer | Survives compaction | Survives a new session | Survives transcript cleanup (30 days) | Seen by sub-agents |
|---|---|---|---|---|
| Files in `meta/`, committed to git | yes | yes | yes | yes, if they read them |
| `CLAUDE.md` pointer (META block) | yes | yes, loaded automatically | yes | yes, loaded automatically |
| SessionStart hook → injects `CURRENT.md` while `Status: active` | yes, re-injected after compaction | yes, on startup and resume | yes | no (it skips sub-agents) |
| Local memory notes (`~/.claude/.../memory`) | yes | yes, the index is loaded | yes, but local and untracked | no |
| Conversation context | summarised, so detail is lost | no | no | no |
| Session transcripts (`*.jsonl`) | yes | yes | **no, deleted after 30 days** | no |

**Rule:** anything worth keeping is written to `meta/` (and committed) during the
discussion, not afterwards. Raw numbers are archived to `meta/sprints/<date>/` before the
transcripts age out.
