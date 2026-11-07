---
name: qa-sweep
description: Run a QA sweep of the current project by launching the qa-spec-conformance, qa-bug-hunter, qa-performance and qa-security subagents in parallel, then write a consolidated index to qa-reports/<date>/README.md. Use when the user asks for a QA pass, bug sweep, audit, or "run the QA agents". Optional args - a scope (a diff range like base...tip, a path or a feature), a subset of agents (spec, bugs, perf, security), paths already security-reviewed (skipped), and whether the full test suite already ran.
---

# QA Sweep

Run the QA subagents against the project in the current working directory (assumed to be the project root) and produce a tidy report directory.

## 1. Prepare

- `DATE=$(date +%F)`; `OUT=qa-reports/$DATE` (if it already exists and has reports, use `qa-reports/$DATE-<HHMM>` so you don't overwrite a previous run). `mkdir -p "$OUT"`.
- Note `git rev-parse --short HEAD` and whether the tree is dirty.
- Parse args:
  - **Scope**: a diff range (`<base>...<tip>`) → every agent reviews only the lines it adds or changes; older code goes in each report's short "Outside the diff" list. Any path, feature name or spec folder → pass it to every agent as its focus.
  - **Agent subset**: `spec`, `bugs`, `perf`, `security` → run only those. Default: all four.
  - **Already reviewed**: paths that had a security review at hand-off → tell every agent to skip them.
  - **Suite already ran**: tell the agents (with its result if given) so they don't run it again.

## 2. Launch agents in parallel

In a **single message**, call the Agent tool once per selected agent (they run concurrently):

| Key | subagent_type | Report file |
|---|---|---|
| spec | `qa-spec-conformance` | `$OUT/spec-conformance.md` |
| bugs | `qa-bug-hunter` | `$OUT/bugs.md` |
| perf | `qa-performance` | `$OUT/performance.md` |
| security | `qa-security` | `$OUT/security.md` |

Prompt each with: the project root, the output directory `$OUT` (tell it to write there), the scope if any, the already-reviewed paths, whether the suite already ran, and "follow your report format exactly; reply with path, counts, top 3."

Wait for all of them to finish. Don't duplicate their work while waiting.

## 3. Consolidate

Read every report that was written. Then write `$OUT/README.md`:

```markdown
# QA Sweep — <project> — <date>
_Commit:_ <sha> (<clean|dirty>) · _Scope:_ <scope or "whole repo"> · _Agents:_ <list>

## Overview
| Report | Critical | High | Medium | Low |
|---|---|---|---|---|
| [Spec conformance](spec-conformance.md) | | | | |
| [Bugs](bugs.md) | | | | |
| [Performance](performance.md) | | | | |
| [Security](security.md) | | | | |
| **Total** | | | | |

## Fix first
Findings that meet the fix bar: a broken acceptance criterion, a security hole or data loss, i.e. Medium and above in the scope (with a diff range: **In diff: yes** only). Ranked by severity × confidence, at most ~10, each as:
`- [ID](file.md#anchor) **Severity** — title — \`path:line\``

## Cross-cutting themes
Findings that appear in more than one report (e.g. the same function flagged as both a bug and a perf issue) — merge and note the IDs. Call out duplicates.

## Backlog groups
The Lows and the below-bar findings, grouped by root cause (one line per group with its IDs), so each group can become one backlog ticket. Findings outside the diff are listed here only by count per report.

## Notes
Anything an agent couldn't verify, agents that failed, and how to re-run (`/qa-sweep <scope> <agents>`).
```

Spot-check the 3 highest-severity findings yourself (open the cited lines) before listing them under "Fix first"; if one doesn't hold up, mark it `(disputed)` and say why.

## 4. Report back

Tell the user the `$OUT` path, the totals table, and the "Fix first" list (or "nothing meets the fix bar"). Don't paste whole reports. Suggest adding `qa-reports/` to `.gitignore` if it isn't there and they don't want reports committed — but don't edit `.gitignore` without asking.
