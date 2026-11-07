# Brief 065-agent-files (Vera, seat dev-4)

- **Feature / branch:** `065-agent-files`, tier **S**, opus medium. Not security-core.
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (detached at `9ff8602`). Base: `9ff8602`
  (sprint branch `sprint-2026-11-07` tip at launch).
- **In parallel:** Tomas (066, check/mutate/facts tools), Nils (067, board hook + query tools),
  Ansel (068, stack/browser/token tools). You document their interfaces from the `contract:*`
  board keys, not from their code; they may still be building.
- **Stories:** sc-526 (3), sc-527 (1), sc-528 (2), sc-532 (1), and the agent-file part of sc-531.
  You move all five to In Progress/Under Review except sc-531, which Nils moves.

## Footprint (yours alone)

- `.claude/agents/developer.md`, `.claude/agents/product-owner.md`, `.claude/agents/scrum-master.md`
- `.claude/skills/team-launch/**`
- `CLAUDE.md` and `AGENTS.md`: **only** a new marked local section outside the generated
  `<!-- gitnexus:start/end -->` block (e.g. `<!-- LOCAL GITNEXUS SCOPE START/END -->`). Explicit
  exception to the protected-file rule for this feature (board `decision:protected-files`).
  Don't touch the SPECKIT or META blocks.
- `sprints/2026-11-07/user-level/**` (new): the qa-sweep skill and the qa-* agent prompts live in
  `~/.claude/skills/qa-sweep/` and `~/.claude/agents/qa-*.md`, outside git. **Don't edit
  `~/.claude`.** Write your proposed full replacements there (same file names) plus a short
  `README.md` saying what changed and why; team-lead applies them after review.
- Not yours: `.specify/memory/constitution.md` (if a line conflicts with D21/D22, post a
  `notice` to Maren), `shortcut-sync.md`, other skills, members' memories.

## Acceptance criteria (verbatim from the stories)

**sc-526 Team testing shape (D21).** Shape (each layer proves what the one before can't, once):
1. Developer: targeted tests while building; one honest contract test per promise the story makes; hand-off receipt = one suite for the touched part (frontend: vitest + build; backend: pytest; config: the targeted tests); no full suites mid-build; mutation only for security/concurrency guards, one bite each.
2. Merge: check receipts per branch, merge all disjoint streams, one full suite at the tip, bisect only on red.
3. One QA read: sweep the sprint diff only; fix bar = broken AC, security hole, data loss (Medium+ in new code); Lows to backlog unless same hunk; code with a P7 security review at hand-off is not swept again.
4. Live pass on real data once at the tip; re-check only when a fix touched that path.
5. Drop: prompt-wording pins except security wording (keep the budget test); two proofs of one claim; docs pass re-verifying facts edited this sprint; tier-L tasks gate; deferred-QA ritual on small sprints; fix rounds when nothing meets the bar.
Files: developer.md, product-owner.md, scrum-master.md, qa-sweep skill + QA agent prompts, team-launch, check.py (receipt by area; check.py itself is Tomas's).
**Done when:** the agent files and skills say this, and the old rules they replace are cut, not left alongside.

**sc-527 GitNexus gates only for code-symbol diffs (D22).** Impact before an edit and detect-changes are required only when a code symbol changes. Not required for config/YAML/dashboard JSON, docs, docstring- or comment-only edits, or a single-component frontend file. detect-changes runs once before hand-off, not at every commit.
Files: CLAUDE.md GitNexus block (the GitNexus analyze/upgrade may regenerate it: put the rule in a marked local section and re-check after upgrades), developer.md, the pre-commit hook if it nags. (Maren checked: `.githooks/pre-commit` runs only the facts hint and the archdocs merge gate, no GitNexus nag; confirm and leave it.)

**sc-528 Product owner process.** Into `product-owner.md` (and team-launch where the lead acts):
- Developers never make credentialed or live calls; the PO never asks them to (Maren asked Nils at #37 despite the rule in her memory).
- Live pre-check slot in briefs: developer posts `live-check:<feature>-pre` with the exact command while building; team-lead runs it at once (Nils; took 7 min, settled europe-west1 before hand-off).
- EXPECT entries pin facts from the stored report (`livecheck.py --facts`), never wording regexes (cooldown regex passed on wording alone).
- Diagnosis tickets are pointed and briefed as spikes, naming the read-only data sources and verification scripts (Ansel: sc-504 was a spike sized as 2 pts build, 40 calls).
- Scope from the steer; if the steer is "plan from the backlog", fill ONE sprint with 4-8 disjoint tier-S streams, not two small sprints (all six: the PO's ~2.5 M and the live pass are per sprint).
- Model per stream: mechanical sub-work (rewording) to a sonnet sub-agent; opus medium unless judgement is needed throughout (Vera).
- Don't re-read full hand-offs already on the board (Tomas).

**sc-532 Scrum master.** File grants keyed per path (`owner:<path>`) for the PO too, so an added file is one post. Tier L: two gates (spec, plan); drop the tasks gate. Seat an SM only when two streams need the same file in the same window, a migration chain, or several gated Spec Kit streams at once (`product-owner.md` tier rules, team-launch).

**sc-531, agent-file part.** No ritual notices: a GitNexus result that never changes a decision is not posted. Agent files: cut what repeats the constitution and skills; mark the rules that bite so a newcomer can tell. Lighter hand-off format. Also document the board addressing from `contract:board-to` (who posts with `--to` whom: grants and answers to the developer they concern) in the PO, SM and developer files.

## Also from the contracts (document, don't build)

- `contract:check-cli` (Tomas): the hand-off receipt by area, the PO's per-branch verify and the one
  full run at the merged tip. Replace today's "full-suite receipt" wording everywhere.
- `contract:facts-cli` (Tomas): the PO passes `--runs <paths the developer runs>` to `facts.py brief`.
- `contract:tool-names` (Nils, Ansel): one line per new tool in developer.md's team-tools list.
- P15 (reserve backfill) stays as it is in product-owner.md; don't touch it.

## Guidance

- **Rewrite, don't append** (steer). Every new rule replaces an old one: find it and cut it. Report
  word counts before and after for each file; the agent files should end shorter.
- The PO-side merge flow becomes: per-branch receipt check, merge all disjoint streams, one full
  suite at the tip, bisect only on red. Keep the D18 hand-off security review; the end sweep then
  skips code it already reviewed.
- Maren's preference for "small sprints" in the deferred-QA rule: keep dedupe (owner's rule), but
  drop the dated breadcrumbs, "Last seen" updates and "Not reported" comments for Lows; group Lows by
  root cause into existing or new `qa-deferred` tickets. Your call on the exact line.
- "Mark the rules that bite": a short marker (e.g. **bold** lead or a "Hard rules" list) for the
  rules whose breach cost a rework round or broke something; plain text for guidance. Keep it simple.
- You may hand mechanical rewording (e.g. the four qa-* prompts) to a sonnet sub-agent over files
  you name; you review and commit.
- Proof for markdown: `grep` that each replaced rule's old wording is gone, plus your AC map
  (file:section per AC line). No pytest run needed (no code).

## Rules for every stream this sprint (D21, D22, steer #1)

- **Context:** this sprint the team builds P14, its own retro. Read
  `meta/sprints/2026-11-05b/retro.md` and the P14 section of `meta/team-optimisation.md` (from
  the main checkout `/home/rudolf/dev/warcraftlogs-agent`, read-only) before you plan.
- **Testing shape (D21, use it already):** targeted tests while you build, one honest contract
  test per promise the story makes, no full suites mid-build, mutation (`mutate.py`) only for a
  security or concurrency guard, one bite each. Hand-off proof: `check.py run <your test
  files> --as <you>` on the committed head, and paste its RESULT line. A targeted run writes no
  receipt today; that's expected. Maren runs the one full suite at the merged tip.
- **GitNexus (D22, use it already):** `impact` before editing an existing Python function or
  class, and `detect-changes` once before hand-off, only when your diff changes code symbols.
  Not for markdown, agent files, skills, YAML or new stand-alone files. Don't post GitNexus
  results that change no decision.
- **Contracts:** the board keys `contract:board-to`, `contract:check-cli`, `contract:facts-cli`
  and `contract:tool-names` fix the interfaces other streams document or use. If your design
  needs a change to a contract you implement, post a `decision` on that same key with the new
  text (it supersedes the old one) before your hand-off; Vera documents whatever the latest
  entry says.
- **Board tests:** never run `board.py init`/`close` in a real checkout: the board root is the
  git common dir shared by every worktree, and `init` switches the live board for the whole
  team. Test board behaviour in a temporary `git init` repo, as `backend/tests/test_team_board.py`
  does.
- **No credentialed or live calls**, no `.env`, no default ports, never push. A check that
  needs the owner's stack: post a `question` with key `live-check:<feature>-pre` and the exact
  command, and team-lead runs it.
- **Tickets:** move your stories to In Progress at the start and Under Review in the hand-off.
- **Hand-off:** about 20 lines: branch, base, head; files; one line per AC with its proof;
  decisions; facts added or fixed; the `Retro:` line. Don't repeat your board `handoff`.
(No team facts are anchored to this footprint.)
