# Brief 027 — Design doc part 1: capability summary and profile write tools

- **Feature:** 027 · **Branch:** `027-design-capabilities-tools` (create it yourself:
  `git -C /home/rudolf/dev/wcl-worktrees/dev-a checkout -b 027-design-capabilities-tools`)
- **Worktree:** `/home/rudolf/dev/wcl-worktrees/dev-a` (track A)
- **Base ref:** `sprint-2026-10-26` @ `cf370e8`
- **Story:** sc-211 (3 pts), Design doc (HTML): self-aware agent, capability summary and
  profile write tools (for the build stories sc-204, sc-205). Read the full story on
  Shortcut (`mcp__shortcut__stories-get-by-id` 211). It lists the design questions and the top nav.
- **Peer:** track B developer on 028 (`dev-b-028`). It writes
  `participants-and-confirmation.html` and **links to your proposal-contract table**.
- **Sprint files:** plan `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-26/plan.md`
  (section 027 and the overlap table), decisions `.../decisions.md` (D4–D6 binding),
  ownership `.../ownership.md`.

## Process (doc-only, decision D3)

No Spec Kit run. Flow:
1. Move sc-211 to **In Progress** (iteration 161 is set already).
2. Explore the real code with GitNexus (`query`/`context`), focusing on `wcl_agent/agent.py`
   (`build_instruction`, `build_agent`), `backend/app/api/profile.py`
   (`_add`/`_patch`/`_delete` and the route handlers), `backend/app/db/repository.py`,
   `backend/app/agent_runner.py` (tenant passed as ADK `user_id`), RLS/tenancy
   (`documentation/multi_tenancy_guide.md`), and `documentation/architecture/*.html`.
3. **Write the proposal-contract table first** and send it to the scrum master as soon as
   it is stable (expected early, before the rest of the doc). The scrum master relays it to
   028. Tell `dev-b-028` the anchor id directly as well. After that, a change to the table goes
   through the scrum master.
4. Write the doc. Send the scrum master an outline or table of contents when you're about halfway
   through. That's the one review checkpoint.
5. Hand-off: commit on your branch (never push), then send the scrum master the branch, commits,
   files changed, and an AC 1–7 mapping (section anchors), plus how you checked
   "no network requests" and 390px.

## Acceptance criteria (verbatim from plan.md)

1. Every design question in sc-211 has a decision or an explicit "Open question" with
   options: the capability summary (generated from the registered tools, injection
   point, token budget, staying correct as tools change), the profile tools (names,
   arguments, results for read / add / update / remove of own characters and friends,
   including roles), two-phase writes (proposal storage, expiry, tenant scoping,
   idempotent execution, per-item result), security (tenant scoping/RLS, own profile
   only, limits, duplicate and realm validation, prompt injection via WCL data such
   as character names), and tests (unit, integration, agent-eval).
2. The change-proposal contract is written **once**, as a table, in this doc
   (id, items to add/update/remove with name, realm, region, class, spec, role, and a
   per-item validation result, plus status and expiry).
3. The design reuses the existing write path in `backend/app/api/profile.py`
   (`_add` / `_patch` / `_delete` behind `add_friend`, `patch_friend`, `delete_friend`,
   `add_own_character`, …) through one shared service. There is no second write path.
4. Each decision lists the alternatives and why, and cites real code, specs, the
   constitution or `documentation/architecture/`. Anything not grounded is labelled
   "Inferred" or "Open question". Every file and function named exists (spot-checked
   at review) or is clearly marked as new.
5. Diagrams: the end-to-end flow for the example request (index.html), a sequence
   diagram "agent proposes → user approves → write → result", and a component diagram
   of the new tool/service pieces. Inline SVG with animated flow arrows, a pause
   control and a `prefers-reduced-motion` fallback.
6. Page conventions: the `<style>` block copied from
   `documentation/architecture/backend-data-infra.html`; standalone HTML with **no
   network requests** (no external `src`/`href`/`@import`); light and dark themes;
   readable at 390px with no horizontal page scroll; the top nav from the story.
7. It follows the product decisions in `decisions.md` (D4–D6).

## Design constraints the scrum master adds (from the plan's overlap table)

- 029 must **not** add WebSocket frames. Design a service function, e.g.
  `execute_proposal(...)`, that 031's transport calls. Frame and transport design belong to 028.
- Decide where proposals live: Postgres (then migration `0016`, `down_revision`
  `"0015_rescan_mplus_runs"`, with tenant RLS like the other tenant tables) or something
  simpler. Justify the choice against constitution III.
- State the capability-summary token budget as a number that 029 can assert in a test.
- No scope creep: design only what sc-204 and sc-205 need. Extras go in an "Open questions /
  follow-ups" section.

## Footprint (tentative grant)

- `documentation/designs/self-aware-agent/index.html` (you own it; 028 only links to it)
- `documentation/designs/self-aware-agent/capabilities-and-tools.html`

Nothing else. No code changes. Don't commit `CLAUDE.md` or `.specify/feature.json`.
No app, DB or ports are needed. To check 390px, render the page with a headless browser if
you have one; otherwise reason from the CSS and say so.
