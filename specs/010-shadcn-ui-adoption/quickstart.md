# Quickstart: Shared UI Component Adoption

**Feature**: 010-shadcn-ui-adoption | **Date**: 2026-10-11

## 0. Baseline (before any change)

```sh
cd frontend
npm ci
npm run build
gzip -c dist/assets/index-*.js | wc -c      # record as BEFORE_GZ
grep -rnE '<(button|input|select|textarea)\b|confirm\(' src --include='*.tsx' | wc -l   # today's count, for the write-up
```

## 1. Install the primitives

```sh
cd frontend
npx shadcn@latest add button input textarea label field native-select dialog alert-dialog tabs table badge alert
grep -rn "lucide-react" src/components/ui || echo "icons ok"     # must print "icons ok" (FR-012)
git diff --stat package.json                                       # expect: + radix-ui only
npx tsc -b
```

If the CLI left `from "cn"` or `from "src/components/ui/…"` imports (it did on
2026-10-11), run `npm uninstall cn` and rewrite them to `../../lib/utils` / `./<file>`.

Then apply the three recorded edits (research R3, R8, R10): strip animation classes from
`dialog.tsx` / `alert-dialog.tsx`, trim `buttonVariants`, add `success`/`warning` to
`badgeVariants`. Add the tokens from `contracts/ui-components.md` §3 to `src/index.css`.

## 2. Run

```sh
docker compose up --build          # backend :8000, frontend :5173
# or, frontend only against a running backend:
cd frontend && npm run dev
```

Sign in at <http://localhost:5173/login>. An admin account is needed for the admin checks.

## 3. Verify per user story

### US1 — consistent forms and buttons

1. Open `/login`, `/accept-invite`, `/reset-password` (the latter two work without a token
   for visual checks; submitting shows the "invalid or expired" error). Fields, labels and
   the submit button are the same component on all three; the form-level error renders in
   the same place and style. Background, card and text are the dark-gold palette, not grey.
2. In the chat header, start a turn: the model picker and PDF/Sign out buttons show the
   shared disabled look and cannot be activated while streaming.
3. On `/profile` → Characters, change a friend's raid role: immediate save, same look as
   the model picker.
4. Composer: Enter sends, Shift+Enter inserts a newline, Send is disabled when empty or
   streaming or disconnected.
5. Tab through each page with the keyboard: every field and button receives a visible
   gold focus ring in reading order.

### US2 — dialogs and confirmations

1. `/profile` → Class Guides → View on a ready guide: focus moves into the dialog, Tab
   cycles inside it, the page behind does not scroll, Escape / Close / backdrop click all
   close it, and focus returns to the View button.
2. Open a long guide: only the dialog body scrolls.
3. Leave a guide open for > 4 s while another guide is generating (list polls): the
   dialog stays open with its content.
4. `/admin/users` → Disable on an active user: an in-app dialog names the email with
   Cancel and a red Disable. Cancel changes nothing. Confirm disables and the row's badge
   turns to the failed tone. The browser's native confirm never appears.
5. Make the request fail (stop the backend, confirm): the dialog closes, the error strip
   appears at the top, the user stays enabled.
6. Sidebar → hover a conversation → ✕: the dialog names the title; Cancel keeps it;
   Confirm deletes it, and if it was active a fresh chat opens.
7. Characters → ✕ on a friend and on the guild: same dialog before anything is removed.
8. Admin → Revoke on an invitation: immediate, no dialog.
9. Press Escape while a confirmed delete is still in flight (throttle the network): the
   dialog stays open until the request resolves.

### US3 — profile tabs

1. Focus the Characters tab, press →: Class Guides is selected and focused; ← returns.
2. Type into the "Add friend" Name field, switch tabs and back: the text is still there.
3. Reload `/profile` with the network panel open: no `/api/guides` request until Class
   Guides is first selected.

### US4 — admin tables, badges, alerts

1. `/admin/users` with ≥ 1 invitation and ≥ 1 user: two tables in the shared style, status
   badges with distinct tones (active vs disabled; open vs expired), header row styled.
2. Trigger an action failure: dismissible alert strip at the top; Dismiss hides it.
3. Narrow the window to ~380 px: tables scroll horizontally inside their card; the page
   does not overflow.
4. Force the degraded model list (stop Vertex access or mock `/api/models` to return
   `degraded: true`): the header shows a warning badge with the same tooltip as before.

## 4. Audits and gates (after the last slice)

```sh
cd frontend
npx tsc -b
grep -rnE '<(button|input|select|textarea)\b|confirm\(' src --include='*.tsx' --exclude-dir=ui
#   → only the allowlist in contracts/ui-components.md §5; "confirm(" never
grep -rnE 'neutral-|indigo-|red-[0-9]' src                      # → empty (SC-005)
grep -rn "lucide-react" src                                     # → empty (FR-012)
npm run build && gzip -c dist/assets/index-*.js | wc -c        # AFTER_GZ ≤ 1.10 × BEFORE_GZ (SC-006)
cd .. && uv run pytest -q                                        # backend untouched, still green
```

Reduced motion: enable "reduce motion" in the OS, open the guide dialog and switch tabs;
nothing animates (there are no animations to disable, research R3).

## 5. GitNexus discipline

Before editing each component: `impact({target, direction: "upstream"})` (results recorded
in plan.md for the six main symbols). Before each commit:
`detect_changes({scope: "all"})` and, after committing,
`node .gitnexus/run.cjs analyze --index-only`.

## Measurements

| Metric | Before (2026-10-11) | After |
|---|---|---|
| `dist/assets/index-*.js` gzip bytes | 450741 | 473626 (+5.1%, gate ≤ 495815) |
| all `dist/assets/*.js` gzip bytes | 1935429 | 1958911 (+1.2%) |
| native-control grep matches (`<button|input|select|textarea`, `confirm(`) in `src/**/*.tsx` | 53 | 11, all on the contract §5 allowlist (3 show-password checkboxes, Sidebar section toggles ×2 + raid item, MessageList ×3, EncounterPicker, FollowUps); `confirm(` 0 |

Final audit output (2026-10-11, after T041):

```text
src/pages/AcceptInvitePage.tsx:101:          <input        # show-password checkbox
src/pages/ResetPasswordPage.tsx:93:            <input      # show-password checkbox
src/pages/LoginPage.tsx:73:          <input               # show-password checkbox
src/components/Sidebar.tsx:79:      <button              # Raids section toggle (FR-015)
src/components/Sidebar.tsx:92:            <button        # raid item (FR-015)
src/components/Sidebar.tsx:106:      <button             # Conversations section toggle (FR-015)
src/components/MessageList.tsx:42,102,179: <button       # message renderer (FR-015)
src/components/EncounterPicker.tsx:30:              <input  # boss-focus checkbox (FR-015)
src/components/FollowUps.tsx:16:        <button          # follow-up chip (FR-015)
```

Palette grep (`neutral-|indigo-|red-[0-9]`) and icon grep (`lucide-react`): empty.
Backend: `uv run pytest -q` → 434 passed, 3 skipped.
