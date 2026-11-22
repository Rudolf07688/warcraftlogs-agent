# Seat review: bounds in briefs and members' goals (P17, P16 step 5), 2026-11-22

Draft change to `.claude/agents/product-owner.md`, for Maren to review read-only before it
lands.

## Why

The P17 pilot (`meta/coaching/pilot-2026-11-22.md`) found missing bounds to be the most common
fix-bar class: 48 rows across 5 seats, with the only Critical. D18 reviews "keep finding no rate
bound and a connection held across a wait" (Maren's own memory). The 11-07b ledger row: the
hostile-input list missed exactly those two classes, which 3 of the 4 D18 reviews then found.
Members can now also hold "Working on" goals that they agree in a 1:1 with team-lead (owner
preference 30). The PO should know about them when briefing.

## Draft 1: a new bullet under "Every brief contains", after "Hostile inputs"

> - **Bounds**, when the stream adds an endpoint, loop, queue, cache, background job, outbound
>   call or anything that grows with traffic or history: list the bound each one needs, one per
>   line, each with its test. Check **time** (timeout or deadline, including shutdown),
>   **size** (payload, field, label, regex input), **rate** (per user or workspace, in-flight
>   cap), **growth** (caches, tags, logs, history), and **held resources** (no connection,
>   lock or lane slot held across an external wait). Drop what doesn't apply. P17 pilot: 48
>   fix-bar findings in 10 sprints, across 5 seats.

## Draft 2: added to the "Seats" paragraph

> `member.py roster` also shows each member's "Working on" goals, agreed in a 1:1 with
> team-lead. When a stream touches a goal's trigger, add one line to the brief:
> "<Name> is working on: <goal>". Pick seats for the work as usual, not to steer anyone
> towards or away from a goal.

## Questions for the reviewer

1. Does Draft 1 earn its place, or does it overlap "Hostile inputs" enough to merge them?
2. Is the trigger list right, too wide (every brief), or too narrow?
3. Draft 2: useful, or noise in the brief?
4. Wording fixes: give them word for word.
