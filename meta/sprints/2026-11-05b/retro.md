# Full-team retro, sprint 2026-11-05b (2026-11-05 evening)

The first retro with the whole team, which the owner asked for on 2026-11-05. Each member was
relaunched read-only by seat and answered in their own voice. In round 1 they had the sprint
numbers, their own retro line, their `member.py lint` lines and the lead's five topics. In
round 2 they had the owner's message on testing, communication and restrictions. Members could
trim only their own memory. The result is **P14** in `meta/team-optimisation.md` (decisions
D21 and D22) and the Shortcut epic "Agent team: ways of working and tools (retro 2026-11-05b)".
Nothing is implemented yet. The owner, verbatim: "I want you to implement all these things, but
not now. Add them to the backlog. Make sure we capture all of these learning ... We want to
adopt the ways of work as well as give the agents the tools they need ... for tomorrow, we
evolve."

## The owner's message (round 2, verbatim)

> It feels like you, as a team, are a little to pedantic on the testing. You each test your own
> work then wa then fix then test then someone else tests etc etc... It's too much. You need to
> test small isolated blocks per developer and the make sure everythng works and that's it. If
> you're confident about the building blocks *with small, useful local tests) then the QA sweep
> shouldn't send everydoby into a rabbit hole.
>
> What are the rest of the teams' feeling around communication and their current abilities and
> restrictions?

On the follow-up the owner said "yes, relax them for non-code diffs, go ahead" about the
GitNexus gates, and approved the round-1 plan ("Yes, I agree with that"). The lead read the
second answer as also covering sc-512, the embedding location.

## Round 1: the sprint and the lead's topics

| Topic | Lead's position | Team | Outcome |
|---|---|---|---|
| 1. Shape | Small fact-loaded streams as the default; maybe two small sprints instead of one big one | **All six disagreed with two sprints**: the PO's fixed work (~2.5 M) and the live pass are paid per sprint. Run 4–8 disjoint streams in one sprint. Maren: scope from the steer; fill from the backlog only when the steer says "plan from the backlog". Vera: small in points isn't cheap when the footprint is wide (064: 2 pts, 26 docstrings in two packages). | One sprint, many disjoint tier-S streams |
| 2. Coordination 35% | Fixed cost, acceptable | Maren and Ilse, independently: the cuttable part is the **full suite at every merge** (each merge moves the tip and voids the next receipt). Merge all disjoint streams, then one suite at the tip, bisect only on red. Tomas: the PO re-reads full hand-offs that are already on the board. Everyone: keep the live pass (it caught the 2.7 s margin). | Lighter merge (P14 §1) |
| 3. EXPECT | Pin facts, not regexes | All agree. Maren writes the EXPECT lines and owns the weak cooldown regex. Nils: pin a stored fact such as `mode=hybrid` in the log. | P14 §2 |
| 4. Tools | mutate.py vitest, npm ci in check.py, prompt-pin helper, lib.sh facts | All agree. Ansel, Maren and Tomas go wider: **brief facts should cover the paths a developer runs** (stack scripts, test libs, what they source), not only the paths they write. Vera: the `tool-docstring-is-prompt` fact should list the pinning test files. | P14 §5 |
| 5. Live calls | Route credentialed calls to team-lead from the start | Maren owns it: the rule was already in her memory and she still asked Nils (#37), so it belongs in the PO agent file. Nils: make a **live pre-check** a standard brief slot. The developer posts `live-check:<feature>-pre` with the exact command while building, and the lead runs it at once (7 minutes this sprint, settled europe-west1 before the hand-off). | P14 §2 |

### Round 1: corrections and additions per member

- **Maren (po):** keep "facts in every brief, use and adds named in the hand-off". The bad
  live call was hers, not the brief's. A board key keeps only its latest entry, so the #27
  grant had to be restated as #28.
- **Ilse (sm, sat out):** seating her would have added 1.5–2.5 M and caught nothing. Seat an
  SM when two streams need the same file in the same window, for a migration chain, or for
  several gated Spec Kit streams. Grants should be keyed **per path** (`owner:<path>`), as
  `scrum-master.md` says, not per feature, so an added file is a single post.
- **Ansel (dev-1):** the port collision cost about 5 calls, not most of his 40. The 40 came
  from sc-504 being a **diagnosis spike pointed as 2 pts of build**: live measurement, digging
  out the plugin's source, two stack scripts, each run with its own wait, and a rebase. The
  PO should mark diagnosis tickets as spikes, and their brief should name the read-only data
  sources and the verification scripts. A fact for the source-map recipe would help.
- **Tomas (dev-2):** confirms the comp:team stale fix in `facts.py anchor_state`. One gap
  remains: a directory anchor `file:.claude/team/` would still go stale on a fact edit (none
  exists yet). Keep the stale and changed lists as the docs queue. Without vitest mutation he
  hand-reverted code to check his frontend tests. He trusts footprint surfacing for
  code-specific facts, but not for general patterns, which he keeps in his memory.
- **Nils (dev-3):** read-only Tempo traces plus unauthenticated timings found the 12 s global
  cold connection without spending a token. **sc-512 recommendation:** make the default
  `kb_embed_location` empty. A pinned `WCL_MODEL_LOCATION` region is then used for embeddings
  too, which respects residency. Only `global` maps to europe-west1, which avoids the cold
  connection. An explicit `KB_EMBED_LOCATION` still wins. That's a few lines plus one test.
  **sc-524:** measure first. A longer keepalive on the embed client probably beats raising the
  3 s deadline.
- **Vera (dev-4, first sprint):** measuring first took about 5 calls and showed that tool
  schemas, not the instruction, were 63% of the fixed prompt. The cost came from the wide
  footprint plus the prompt-pin hunt (pins in five test files, some across line breaks).
  **Opus high was more than needed.** Next time: opus medium, with the mechanical docstring
  rewording given to a sonnet sub-agent. Helper sketch: `assert_prompt_pins(text, PINS)`. It
  takes one registry mapping each clause to its spec id, collapses whitespace on both sides,
  and on a miss prints the clause, its spec id and the nearest text found. Onboarding was
  clear apart from the missing pin list.

## Round 2: testing, communication, restrictions

### Testing: where each member tests the same thing twice

| Member | Repeats | Drop | Must stay |
|---|---|---|---|
| Maren | Full suite at every merge. A security review at hand-off **and** in the end sweep. A fix round when the sweep found 0 High (Nils's fixes were robustness work she had labelled correctness). | Fix bar: a broken AC, a security hole or data loss; everything else is a ticket. One security pass on a small sprint. | One suite on the combined tree. The live pass on real data. Her AC check (it caught an AC written for HTTP when chat runs over a WebSocket). |
| Ilse | At each hand-off she re-ran the full suite on a trial merge and re-ran detect-changes, both of which the developer had already done. Her tasks gate repeats the plan gate. | Check receipts per branch, merge, one suite at the tip. Two gates (spec, plan), not three. | One suite on the integrated tip. Her independent security review on security-core work (on 044 it found the two best issues), with the end sweep then **skipping code she has already reviewed**. |
| Ansel | Full suite three times on a YAML/JSON-only change (pre-commit, receipt, post-rebase). sc-508 proven twice: a static test plus a busy/idle stack run. Several mutation bites per test. | Targeted tests plus one receipt. Drop the stack half of sc-508. One bite per new test. | One real-stack check where the bug sits in vendor code (Grafana's node math): no unit test can reach it. His stream had no QA findings; his waste was his own re-runs, not QA rabbit holes. |
| Tomas | 2344 backend tests for a frontend-only story, which Maren then ran again. Six guards mutation-checked where two would do. The docs pass re-verified facts whose authors had just edited them. | Frontend story: vitest plus the build is the receipt. | **Partial disagreement with the owner.** The sweep found BUG-002 (a partial answer landing in the wrong chat). His 13 tests were thorough on the wrong axis: none switched chats mid-turn. Building blocks alone don't show how they combine, so he'd keep one integrated check and the live pass. |
| Nils | 11 mutate runs. Full suites mid-build. | Mutation only for security and concurrency guards. Targeted tests while building, one full run for the receipt. | An independent read of new concurrency and security code: two of his three findings (BUG-003, BUG-005) were real Mediums **he should have caught** with one honest contract test each. His test checked how he'd written it, not what "bounded at 5" means. BUG-006 wasn't worth a fix. Sweep only new code, fix only Medium and above, Lows to the backlog unless in the same hunk. |
| Vera | Prompt-pin tests check that a sentence is present, not behaviour; they were her stream's biggest single cost. Four mutate runs on one budget test. Full suite before hand-off, then at merge, then QA, then the live pass, for a docstring-only stream. | Most prompt pins; keep only those guarding security wording (the untrusted-data rules). One bite. Targeted tests plus one run at the tip. | The prompt-size budget test (a real property; without it the prompt grows back). Eval markers and the live pass carry behaviour. |

**Lead's own share.** My tools and rules set much of this volume: a full-suite `check.py`
receipt as the hand-off proof, `mutate.py` presented as the default, mandatory GitNexus gates
everywhere, and the live re-check after every fix round. A tool that is always required
becomes a ritual, so scope a rule to where it bites.

### Communication

- **Works (all):** briefs that carry their facts; plans posted early on the board (Vera's
  measured table, Tomas's plan post); short hand-offs that map each AC; Maren answers within
  minutes; seam contracts written before launch (Ilse, tier L 11-01: three streams, almost no
  blockers).
- **Costs time:**
  - **Every board entry reaches every agent** through the hook (Ansel, Maren). Most of it is
    unrelated to their stream, and the PO's long live-check questions and restated grants add
    noise.
  - **Ritual posts:** Tomas posted the detect-changes "CRITICAL = App component" notice twice,
    a signal that never changes.
  - **Repetition:** briefs and agent files repeat the constitution and skills. A newcomer
    can't tell which rules bite (Vera, Ilse).
  - **Grants** restate the whole owner list (Maren, Nils; fix: per-path keys).
  - The hand-off format rules take a few calls (Ansel).
  - Board rounds caused by a request that clashed with a rule (Nils).

### Restrictions and abilities

- **Most cost for least gain:**
  - **GitNexus impact plus detect-changes on non-code diffs** (Ansel: YAML, about 6 calls;
    Vera: docstring-only, CRITICAL on 28 flows; Tomas: a single frontend component, always
    CRITICAL). Nils: impact before an edit earns its keep (`genai_client` has 17 callers),
    detect-changes before every commit doesn't; once before hand-off is enough. **Owner
    approved relaxing for non-code diffs (D22).**
  - **Three gates per tier-L feature** (Ilse).
  - **The deferred-QA ritual on a small sprint:** matching each Low by meaning, dated
    comments, "not reported" notes (Maren).
- **Missing tools:**
  - a stack-up helper that picks free ports and writes the env file (Ansel)
  - a headless browser on the developer's own port, since the drop test was only proven in the
    lead's browser (Tomas)
  - an offline token counter for a chat request, instead of a hand-rolled chars/4 (Vera)
  - a read-only Tempo/Loki query helper, instead of hand-rolled curl through the Grafana proxy
    (Nils)
  - "is this finding in this sprint's diff or older code?" (Maren)
- **Keep even though they cost (unanimous):** no push; no `.env` access; no credentialed calls
  by developers ("the lead batching those calls is cheaper", Tomas); one's own worktree and
  file footprint; never granting a file twice (Ilse); one rework round (Maren).

## Memory changes (each member's own, committed b91b4d9)

| Member | Before → after (words) | What |
|---|---|---|
| Maren | 496 → 493 | Cut the Labels line. Kept the live-call rule as a rule for herself. Added the EXPECT and brief-facts lessons. Dropped the tier-L spawn line. |
| Ilse | 330 → 339 | Cut four lines now covered by tools. Kept the sequencing judgment. Added per-path grants and when to seat an SM. |
| Ansel | 471 → 353 | Cut seven lines covered by facts. Kept the Alloy reload line (`mutate.py` doesn't POST the reload) and the line on how Maren works. |
| Tomas | 466 → 416 | Cut four code-specific lines. Kept three general patterns. |
| Nils | 367 → 341 | Cut two lines; lint is now 0. |
| Vera | 98 | No change. |
