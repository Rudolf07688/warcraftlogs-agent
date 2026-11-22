# coaching

Team-lead's teaching loop (P17 in `meta/team-optimisation.md`, owner preference 30).

| File | What it holds |
|---|---|
| `ledger-*.jsonl` | Critique rows extracted at wrap-up: sprint, seat, observer, class, severity, ref, quote |
| `pilot-2026-11-22.md` | The first extraction over 11-01..11-20 and what it showed (person and system rules) |
| `1on1-<date>-<name>.md` | A 1:1 brief and its outcome; the first one is the template |
| `review-<date>-*.md` | Seat reviews of rule changes that came out of coaching |
| `goals-log.jsonl` | Closed "Working on" goals (`member.py goal close`): graduated, dropped or recurred |

**Extraction brief** (one sonnet pass per sprint at wrap-up). For each piece of critique of an
agent's work, write one JSONL row: `sprint, seat, name, stream, observer, class, habit,
severity, fix_round, polarity, summary, ref, quote`. The seat is whoever wrote the
code, brief or rule (not who found it); a vague brief is the PO's, an agent-file rule
team-lead's. `habit` is the moment-of-work behaviour in about 10 words ("new path shipped
without a time/size/rate bound"). The classes are the ones in the pilot ledger; `other:<slug>`
when none fits. Sources: `meta/sprints/<date>/board.jsonl`, `sprints/<date>/qa-triage.md`,
retro files, the team report, `qa-reports/<date>*`.

Members' "Working on" goals live in their own `meta/team/<seat>.md`, written by them only.
