# Full-team retro, sprint 2026-11-07 (round 1)

The second full-team retro, held the same evening while the sprint was fresh (owner: "prepare
for a retro with the team while things are fresh in memory"). All six members were relaunched
read-only by seat with `retro-brief.md` (the numbers plus five topics). Ilse sat the sprint
out but reviewed her rewritten agent file. Members could edit only their own memory. Round 2
is the owner's.

## Round 1, by topic

| Topic | Team | Team-lead | Proposed outcome |
|---|---|---|---|
| 1. Testing shape: 8 fix-bar findings in guard code | **Unanimous: keep D21.** The cheap catch is in the building block, not a D18 review per branch. Maren: the brief lists the hostile inputs (`\` URL parser differential, newline or leading `-` in args, redirects and subresources, identity read from free text, compose reading `.env` via unselected services); 5 of 8 were those. Vera: `developer.md` never says what to do with a security-core brief, so add a hard rule: one test per named attack path, one `mutate.py` bite per guard. Tomas: for any artefact another agent trusts (receipt, alias, cursor), write the forged-input test first; mutation proves a guard bites, not that it can't be bypassed. Ansel: probe a guard at its point of effect (what Chrome fetched, what compose read), not the input string. Nils: the High was a lesson already in his memory; only a brief prompt at the moment of work makes it stick. Ilse: the same three guards were written four times; one shared guard helper with its own adversarial tests. Maren: BUG-001 and BUG-004 were plain logic bugs, and the end sweep is the right place for those. | I over-reached: right after the merge I made team tools that guard secrets, ports or identity D18 security-core, which adds a ~100k review per branch. The team's answer is cheaper and aimed at the cause. | Hostile-input rows in the brief (PO), a developer hard rule for security-core and trust artefacts, D18 kept for app security-core only; a shared guard helper to the backlog |
| 2. Contracts before launch | **Unanimous: a standard PO step** whenever two streams share a format, flag or file. A contract names producer, consumers, the exact format, the base ref it holds on (a flag the sender's base lacks is "a wish, not a contract", Maren), one concrete example (Nils) and the test that pins it (Tomas). When the build differs, an "as built" amendment goes on the same key (Vera: that is what let her document four tools unread). | Agree; it was the cheapest coordination this sprint. | `product-owner.md` §3 step with those fields |
| 3. Tools now on main | Use: `check.py`, `mutate.py`, `facts.py`, `pg.py` (all devs), `stack.py` from worktrees (Ansel, Tomas, Nils), `browse.py` for UI (Ansel, Vera), `obsq.py` (Nils, Tomas, Maren for spikes), `indiff.py` (Maren, Nils at triage), `tokens.py` (only Vera, for prompt work). Missing: `board.py replay` of a filter over a real board export (Nils); `browse.py` wait for rendered content or a selector count (Ansel; my live note); a drift check that every flag named in the agent files still appears in the tool's `--help` (Vera); a footprint check that a diff stays inside its grants and no two grants overlap (Ilse); `mutate.py` DOES NOT BITE should mention a second guard layer (Ansel). | Agree with all five gaps; most are small. | One grouped backlog ticket, deduplicated against sc-538..542 |
| 4. Rewritten agent files | Developers and PO: nothing cut that bites; hard rules 3, 6, 7 earn their place. Gap: the security-core rule above (Vera). Ilse: `scrum-master.md` sends her to the PO's merge flow, which assumes disjoint streams, the one case she's never seated for. Three gaps: a re-sequenced stream's base moves to the first merge commit and its receipt is re-earned after rebase; the tip run needs `--pg` and a single-alembic-head check per migration link; her product questions to the PO can go unseen (the PO's wait watches only its developers). Ritual left: `model:<NNN>` posts that repeat the brief, the old `SPAWN-REQUEST` paragraph. Maren: the facts paste is near-ritual when empty (already "leave it out"). | Ilse is right, and I missed it in my review: I read her file for length and tone, not against the flow it delegates to. | Fix `scrum-master.md` (three gaps, cut two rituals) |
| 5. Next app sprint | **Unanimous:** about 23 pts of app work; the tool tickets sc-538..542 as P15 reserve stories, not fill (each ≤ 3 pts; Ansel volunteers for 538/540, Tomas names 541). Measure as 11-05b: M/pt, build calls/pt, developer full suites (target 0), fix-bar findings per point; Maren: cost per point **by stream type**, so tooling and app work aren't averaged. Ilse: seat an SM only if a trigger truly fires. | Agree. | The steer for the next app sprint |

## What members want the owner to hear

- **Maren:** the cheap sprint came partly from the work itself; judge P14 on the next app sprint.
- **Nils:** the High was his and his memory already warned of it; a memory line doesn't help
  unless the brief prompts it at the moment of work.
- **Tomas:** BUG-004 was his: test what the consumer relies on, not just what the producer writes.
- **Ansel:** the fresh-agent fix round worked: 070 took about 7 minutes to hand-off.
- **Vera:** documenting from board contracts was cheap; it only holds if amendments land on the
  same key. She'd rather have a drift check than more reading.
- **Ilse:** her file was cut well but inherits a merge flow written for the case she's never in.

## Retro lines, revised

- Maren: "brief their attack paths" now means "list the hostile inputs to test".
- Vera: change: `developer.md` should turn the brief's attack paths into tests.
- Tomas: change: for every artefact another agent trusts, write the forged-input test first.
- Nils: change: replay the real board through any filter before hand-off; identity from the launch, not from any command.
- Ansel: probe a guard at its point of effect.
- Ilse: seat a coordinator only for overlap, and then make the overlap rules explicit.

## Memory changes (each member's own)

Tomas cut 3 lines now in facts (406 words). Maren cut 3 lines now in `product-owner.md`, added
her hostile-input checklist (466). Ilse cut 2 covered lines, added the sequenced-stream base and
migration-chain lessons (317). Nils, Ansel and Vera unchanged (Ansel keeps two lint-flagged
lines because `mutate.py` doesn't yet cover them; Maren notes a lint false match on
`guards.py`).

## Card round (owner: "reflect on their agent card ... make changes as they please")

Each member edited only their own card (`meta/team/<seat>.md`), with `retro.md` and P16 to hand.
Mostly they moved codebase lines out of memory (now team facts, soon hook-injected) and put
their retro lesson in. Ilse, Maren, Tomas and Ansel rewrote their `about` line; Nils and Vera
kept theirs. Four members report `member.py lint` false matches: a line mentioning the words
"mutation" or "guard" is flagged as covered by `mutate.py` or `guards.py`.

**Proposals for `developer.md` and `product-owner.md` (feed P16 step 1, reviewed by the affected seats):**
- Vera: the security-core and trust-artefact hard rule.
- Tomas: one test from the consumer's side for each shared format a stream produces.
- Ansel: assert a guard where it takes effect (what was fetched, read or executed), not the input string.
- Nils: replay real data (logs, a board export) through any filter or rule before hand-off.
- Maren: the hostile-input list, the contract step, and her wait also watching Ilse's questions when she's seated.
- Ilse: the three `scrum-master.md` gaps.

**Richer agent cards: the team's view, parked.** The owner, after seeing it: "I like the small identity
cards we have now. We can slowly expand later if we must." Kept for later:
- The most-wanted field is a generated "code I've worked in" (Ansel, Tomas, Nils, Maren).
- Next: fix-bar findings by hazard class, per point and by stream type, with sample counts.
- Cut: model and effort, and "the work you want".

