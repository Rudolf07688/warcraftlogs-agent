# Sprint 2026-11-07 plan: the team builds P14 (epic 525, iteration 536)

PO: Maren. Branch `sprint-2026-11-07`, base `9ff8602`. Steer: board #1 (`steer`).
Goal: adopt the retro's ways of working (D21 testing shape, D22 GitNexus for code only, PO
process, SM rules, quieter board) and give the team the tools it asked for. 20 pts.

## Stories (ticket source for this sprint; copied once from Shortcut)

| id | Name (plain) | Pts | Stream |
|---|---|---|---|
| sc-526 | Team testing shape: building blocks, then the whole, once (D21) | 3 | 065 (agent files); receipt part in 066 |
| sc-527 | GitNexus gates only for code-symbol diffs (D22) | 1 | 065 |
| sc-528 | PO process: live-call rule, live pre-check slot, fact-pinned live checks, spikes, scope and model per stream | 2 | 065 |
| sc-532 | Scrum master: grants per path, two gates, when to seat one | 1 | 065 |
| sc-531 | Less board noise: entries reach only the agents they concern; no ritual notices; leaner agent files | 3 | 067 (hook); agent-file part in 065 |
| sc-530 | Test tools: mutate.py for vitest, npm ci in check.py, receipts by touched area | 3 | 066 |
| sc-529 | Briefs carry facts for the paths a developer runs | 2 | 066 |
| sc-533 | New tools: free-port stack helper, own headless browser, offline token counter | 3 | 068 |
| sc-537 | New tools: read-only trace/log query, finding-in-diff check (split from sc-533) | 2 | 067 |

ACs (verbatim essentials; full text lives in each brief):
- **526** Shape: (1) developer: targeted tests while building; one honest contract test per promise; hand-off receipt = one suite for the touched part (frontend: vitest + build; backend: pytest; config: targeted tests); no full suites mid-build; mutation only for security/concurrency guards, one bite each. (2) Merge: check receipts per branch, merge all disjoint streams, one full suite at the tip, bisect only on red. (3) One QA read: sweep the sprint diff only; fix bar = broken AC, security hole, data loss (Medium+ in new code); Lows to backlog unless same hunk; P7-reviewed code not swept again. (4) Live pass once at the tip; re-check only when a fix touched that path. (5) Drop: prompt-wording pins except security wording (keep the budget test); two proofs of one claim; docs pass re-verifying facts edited this sprint; tier-L tasks gate; deferred-QA ritual on small sprints; fix rounds when nothing meets the bar. Files: developer.md, product-owner.md, scrum-master.md, qa-sweep skill + QA agent prompts, team-launch, check.py. **Done when** the agent files and skills say this and the old rules they replace are cut.
- **527** impact before an edit and detect-changes only when a code symbol changes; not for config/YAML/dashboard JSON, docs, docstring/comment-only edits, or a single-component frontend file; detect-changes once before hand-off, not every commit. Files: CLAUDE.md GitNexus rule in a marked local section, developer.md, pre-commit hook if it nags.
- **528** into product-owner.md (and team-launch where the lead acts): developers never make credentialed/live calls and the PO never asks; live pre-check slot (`live-check:<feature>-pre`, lead runs at once); EXPECT pins facts from the stored report (`livecheck.py --facts`), never wording; diagnosis tickets pointed and briefed as spikes naming read-only data sources and verification scripts; scope from the steer, backlog sprints = one sprint of 4-8 disjoint tier-S streams; mechanical sub-work to a sonnet sub-agent, opus medium unless judgement throughout; don't re-read full hand-offs already on the board.
- **532** grants keyed per path (`owner:<path>`) for the PO too; tier L two gates (spec, plan); seat an SM only for same-file-same-window, a migration chain, or several gated Spec Kit streams (product-owner.md tier rules, team-launch).
- **531** hook delivers only what concerns the reader (own keys and files, steer, decisions to all, answers to its questions); no ritual notices; agent files cut what repeats the constitution and skills and mark the rules that bite; lighter hand-off format; measure board entries read per agent before/after (`usage.py --context`).
- **530** mutate.py supports vitest; check.py runs `npm ci` when node_modules is missing; check.py receipt by touched area (frontend → vitest + build; backend → pytest; config → named targeted tests).
- **529** `facts.py brief` takes the paths a developer runs (e.g. `--runs`); add facts: Grafana plugin source-map recipe (Ansel), pinning test files on `tool-docstring-is-prompt` (Vera's list); fix the directory-anchor stale gap (`file:.claude/team/` goes stale on a fact edit).
- **533** (1) stack-up helper picks free ports, writes the env file; (2) headless browser on the developer's own port; (3) offline token counter for a chat request.
- **537** (4) read-only Tempo/Loki query helper; (5) "is this finding in this sprint's diff or older code?" for triage.

## Features (all tier S, opus medium, no SM, none security-core)

| Feature | Dev (seat, worktree) | Stories | Footprint |
|---|---|---|---|
| 065-agent-files | Vera (dev-4, dev-a) | 526, 527, 528, 532, 531 agent part | `.claude/agents/{developer,product-owner,scrum-master}.md`, `.claude/skills/team-launch/**`, CLAUDE.md + AGENTS.md local GitNexus section, `sprints/2026-11-07/user-level/**` |
| 066-test-tools-facts | Tomas (dev-2, dev-b) | 530, 529, 526 receipt | `.claude/team/{check,mutate,facts}.py`, their tests, fact `tool-docstring-is-prompt` |
| 067-board-relevance-tools | Nils (dev-3, dev-c) | 531, 537 | `.claude/team/board.py`, new `obsq.py`, `indiff.py`, their tests |
| 068-stack-browser-tokens | Ansel (dev-1, dev-d) | 533 | new `stack.py`, `browse.py`, `tokens.py`, their tests, new fact (source-map), frontend manifests if needed |

Contracts posted before launch: `contract:board-to`, `contract:check-cli`, `contract:facts-cli`,
`contract:tool-names`. User-level files (`~/.claude` qa-sweep skill and qa-* agents) are proposed
as files under `sprints/2026-11-07/user-level/`; team-lead applies them.

## Order

All four in parallel (disjoint). Merge order as hand-offs land; one full suite at the tip
(D21). Then live-check questions for stack.py and browse.py, QA sweep of the sprint diff,
fix round only if something meets the bar, docs + facts pass, review.

## Risks / drop first

- Hook filter hides a blocker or answer → coordinators keep the full feed; tested in a temp repo.
- Agent-file rewrite drifts from the tools built in parallel → contracts on the board; Vera follows the latest entry.
- Drop first: token counter (533 item 3), then finding-in-diff (537 item 5).
