---
name: qa-sweep
description: Run a full QA sweep of the current project by launching the qa-spec-conformance, qa-bug-hunter, qa-performance and qa-security subagents in parallel, then write a consolidated index to qa-reports/<date>/README.md. Use when the user asks for a QA pass, bug sweep, audit, or "run the QA agents". Optional args - a scope (path/feature) and/or a subset of agents (spec, bugs, perf, security).
---

# QA Sweep

Run the QA subagents against the project in the current working directory (assumed to be the project root) and produce a tidy report directory.

## 1. Prepare

- `DATE=$(date +%F)`; `OUT=qa-reports/$DATE` (if it already exists and has reports, use `qa-reports/$DATE-<HHMM>` so you don't overwrite a previous run). `mkdir -p "$OUT"`.
- Note `git rev-parse --short HEAD` and whether the tree is dirty.
- Parse args:
  - **Scope**: any path, feature name or spec folder → pass it to every agent as its focus.
  - **Agent subset**: `spec`, `bugs`, `perf`, `security` → run only those. Default: all four.

## 2. Launch agents in parallel

In a **single message**, call the Agent tool once per selected agent (they run concurrently):

| Key | subagent_type | Report file |
|---|---|---|
| spec | `qa-spec-conformance` | `$OUT/spec-conformance.md` |
| bugs | `qa-bug-hunter` | `$OUT/bugs.md` |
| perf | `qa-performance` | `$OUT/performance.md` |
| security | `qa-security` | `$OUT/security.md` |

Prompt each with: the project root, the output directory `$OUT` (tell it to write there), the scope if any, and "follow your report format exactly; reply with path, counts, top 3."

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
Top ~10 findings across all reports, ranked by severity × confidence, each as:
`- [ID](file.md#anchor) **Severity** — title — \`path:line\``

## Cross-cutting themes
Findings that appear in more than one report (e.g. the same function flagged as both a bug and a perf issue) — merge and note the IDs. Call out duplicates.

## Notes
Anything an agent couldn't verify, agents that failed, and how to re-run (`/qa-sweep <scope> <agents>`).
```

Spot-check the 3 highest-severity findings yourself (open the cited lines) before listing them under "Fix first"; if one doesn't hold up, mark it `(disputed)` and say why.

## 4. Report back

Tell the user the `$OUT` path, the totals table, and the top 5 items. Don't paste whole reports. Suggest adding `qa-reports/` to `.gitignore` if it isn't there and they don't want reports committed — but don't edit `.gitignore` without asking.
