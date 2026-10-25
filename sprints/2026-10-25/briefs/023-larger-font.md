# Brief 023 — Slightly increase the default font size (stretch, sc-152)

| Field | Value |
|---|---|
| Feature number | 023 |
| Branch | `023-larger-font` (set `GIT_BRANCH_NAME=023-larger-font` for `/speckit-specify`) |
| Spec dir | `specs/023-larger-font/` |
| Worktree | `/home/rudolf/dev/wcl-worktrees/dev-b` (track B) |
| Base ref | `sprint-2026-10-25` tip (the worktree is detached there) |
| Model / effort | sonnet / medium |
| Shortcut stories | sc-152 (1) |
| Peer developer | `dev-a-021` (track A, 429 fallback; it holds the frontend files listed below) |
| Scrum master | `scrum-master` (your only channel upward) |
| Plan | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/plan.md` ("Stretch") |
| Ownership ledger | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/ownership.md` |
| Decisions | `/home/rudolf/dev/wcl-worktrees/sprint/sprints/2026-10-25/decisions.md` (entry 29 pulls sc-152 in) |

## Acceptance criteria (product owner, verbatim)

1. The base font size goes up one step, in one place: the root/base size in index.css or
   styles.css. No per-component overrides.
2. At 1280px and 390px there's no horizontal overflow or clipped text in the sidebar
   (including the new pin buttons), the composer, the welcome panel (raid and M+ cards)
   and the chat messages. Screenshots or a short note from the dev are fine.
3. The frontend build is green.

It must not touch 021's files: App.tsx, types.ts, wsClient.ts, MessageList.tsx and
toolLabels.ts.

## Light flow

This is a 1-point CSS change, so the Spec Kit flow is short: `/speckit-specify`, then one
clarify message to me (only if needed), then `/speckit-plan` and `/speckit-tasks`
together, a short checkpoint, and implement. One gate message per step is enough.

## Known wrinkle (raise it at clarify)

`frontend/src/styles.css` sets about 20 hard-coded `px` font sizes (e.g. 11px, 12px,
13px, 14px, 14.5px) on components. A single root change only scales what uses
`rem`/`em` or inherits. If AC 1 ("one place") can't reach the chat and sidebar text
without touching those `px` rules, send me the options. Options include converting the
`px` sizes to `rem` (one mechanical pass, same rendered size at the old root) and then
raising the root once, or a CSS variable scale. I'll take it to the product owner. Also
check Tailwind's `text-*` utilities in components (they're `rem`-based).

## Tentative footprint

- `frontend/src/styles.css`, `frontend/src/index.css`, `specs/023-larger-font/**`.
- **Not yours:** `frontend/src/App.tsx`, `types.ts`, `api/wsClient.ts`,
  `components/MessageList.tsx`, `toolLabels.ts` (021). Any other component file needs a
  grant first.

## Notes

- Visual check: run `npm run dev` (Vite) on port **18023** (not the default), or a
  `vite preview` of the build. The backend isn't needed to judge layout, since the auth
  shell and the static layout render. If you need the backend for logged-in screens, ask
  me. Screenshots can come from a headless browser if one is available; otherwise send
  a careful note on what you checked and how.
- No backend changes, so `pytest` should stay at the sprint baseline (1022/3/1).
- Shortcut: move sc-152 to In Progress when you start. Reply "ACK" to every grant.

## Product owner's pre-answer (decision 30, verbatim intent)

1. First commit: a mechanical px→rem pass over the font-size declarations in `styles.css`
   and `index.css`. It must render identically at the current root, and you show that by
   comparing before and after (computed sizes or screenshots).
2. Second commit: one root bump, one step.

Scope is font sizes only. Spacing, borders and layout px stay as they are. ACs 1–3 still
apply. The estimate stays at 1. If something would really push it past that, ask
before widening the scope.
