# Retro brief, sprint 2026-11-07 (round 1)

Read-only retro. The owner asked for it while the sprint is fresh. You answer in your own voice;
team-lead relays every answer side by side with its own view, and the owner may open a round 2.
You may edit **only your own memory** (`member.py remember --seat <you>`), and only if a line
is now wrong or covered by a fact or agent file (`member.py lint --seat <you>` lists them).
Nothing else: no commits, no board posts, no edits to any other file.

## The sprint in numbers

- P14, the team built its own retro: 20/20 pts, four tier-S streams in parallel (Vera agent
  files, Tomas test tools + facts, Nils board filter + obsq/indiff, Ansel stack/browse/tokens),
  49 min from launch to review. Merged to main 23c73aa and pushed; all stories Done.
- 11.2 M, **0.56 M/pt**, the cheapest sprint yet (11-05b: 1.19). Build 0.20/pt (11-05b: 0.50),
  10.6 build calls/pt (11-05b: 15–40). PO 0.15/pt (was 0.25). Coordination share 42% (35%),
  but per point it fell from 0.42 to 0.24. Cold cache 0.48. Mostly stdlib Python tooling,
  which is cheap by type: the next app sprint is the real test.
- D21 first run: 2 full suites, both at the tip; none by developers (11-05b: ~7 PO side plus
  2–3 per developer).
- QA sweep (bugs + security, sprint diff only): 1 High + 8 Mediums; 1H + 7M met the fix bar,
  **all in team tools that guard `.env`, loopback or board identity**. One fresh fix round
  (1.21 M). The old hook's alias bug renamed Maren, Nils and both QA agents live.
- After the merge, team-lead added to `product-owner.md`: team tools that guard a secret, a
  port or an agent's identity are D18 security-core (review at hand-off, attack paths in the
  brief). The QA prompts and qa-sweep skill now live in git as project copies
  (`.claude/agents/qa-*.md`, `.claude/skills/qa-sweep/`).
- Next app sprint: the first with the P15 reserve rule (plan about 23 pts plus 1–2 reserve
  stories of ≤ 3 pts the PO may launch when a developer hands off early).

Read if you need more: `meta/sprints/2026-11-07/team-report-body.html` (cost per agent, P14
measures), `meta/sprints/2026-11-07/board.jsonl` (the sprint board),
`sprints/2026-11-07/qa-triage.md`. Don't read source code unless a topic truly needs it.

## Team-lead's topics (answer each in 1–3 sentences; skip one that isn't yours)

1. **Testing shape (D21).** It held on cost, but 8 fix-bar findings reached the end sweep, all
   in guard code. Is "security-core + attack paths in the brief + D18 review at hand-off" the
   right fix, or would something cheaper in the building-block layer have caught them?
2. **Contracts on the board before launch.** Three of you named `contract:*` keys as the thing
   to keep. Should the PO make "post the contract before launch" a standard step for streams
   that share a format, and what must a contract name (Ansel: only flags the sender's base has)?
3. **The new tools, now on main.** Which will you actually use in the next app sprint, which
   won't you, and what's still missing? (Note: `stack.py` refuses any checkout with a `.env`,
   so it runs from worktrees only.)
4. **The rewritten agent files** (`developer.md` hard rules, `product-owner.md`,
   `scrum-master.md`). Is anything cut that will bite, or anything left that is still ritual?
5. **The next app sprint.** What should the PO do differently from 11-05b so we can tell
   whether P14 worked (steady ~23 pts, reserve stories, the deferred tool tickets sc-538..542)?

## Your answer (your final result, at most about 250 words)

- One line per topic you have a view on.
- Your sprint retro line, if you'd now change it.
- One thing you want the owner to hear, in your own words.
- Memory: "unchanged" or what you cut and why.
