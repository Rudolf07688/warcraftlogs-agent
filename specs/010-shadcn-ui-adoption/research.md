# Research: Shared UI Component Adoption

**Feature**: 010-shadcn-ui-adoption | **Date**: 2026-10-11

All Technical Context items were resolvable from the repository and the shadcn registry
(queried through the shadcn MCP server); no NEEDS CLARIFICATION markers remained after
the spec's clarification session. Each entry below records a decision the implementation
depends on.

## R1. How the components get into the repo

- **Decision**: run `npx shadcn@latest add button input textarea label field native-select
  dialog alert-dialog tabs table badge alert` from `frontend/`, committing the generated
  files under `src/components/ui/` and the `radix-ui` dependency it adds. `components.json`
  is already correct (`style: new-york`, `tsx`, `cssVariables: true`, `css: src/index.css`,
  aliases to `src/components/ui`, `src/lib/utils`, `iconLibrary: react-icons`) and is not
  changed.
- **Rationale**: the registry view (MCP `view_items_in_registries`) lists each item's
  dependencies as `cn` plus, for button/label/dialog/alert-dialog/tabs/badge, `radix-ui`
  (the unified package). Nothing pulls `lucide-react` as a dependency because the CLI
  rewrites icon imports for the configured icon library. One command, one new package.
- **Alternatives considered**: copying component sources by hand from the registry
  (same result, loses the icon rewrite and the dependency bookkeeping); writing our own
  primitives (that is the situation being replaced).
- **Follow-up check**: after the add, `grep -rn "lucide-react" src/components/ui` must
  be empty; if a file still imports lucide, swap to the `react-icons/lu` icon of the same
  name (e.g. `LuX`, `LuChevronDown`).
- **What actually happened (2026-10-11, shadcn CLI via `npx shadcn@latest`)**: the CLI
  (a) did *not* rewrite the two lucide imports (`dialog.tsx`, `native-select.tsx`) despite
  `iconLibrary: react-icons` — swapped to `LuX` / `LuChevronDown` by hand; (b) resolved the
  `utils` alias to a literal npm package named `cn` (installed it, imported `from "cn"`) and
  emitted absolute `from "src/components/ui/…"` imports, because the project has no
  `@/` tsconfig path alias — uninstalled `cn`, rewrote to relative imports; (c) also added
  `separator.tsx` as a dependency of `field`. Any future `shadcn add` must repeat (a)+(b),
  or the project should add a `@/*` path alias to `tsconfig.json` and `vite.config.ts`
  (deferred, out of scope here).

## R2. Theme tokens the components read, and two name collisions

- **Decision**: extend `index.css` (the declared source of truth for the look) with the
  shadcn token set, mapped into Tailwind via the existing `@theme inline` block:

  | shadcn name | value (Tavern Hearth) | note |
  |---|---|---|
  | `--card-foreground` | `var(--foreground)` | |
  | `--popover` / `--popover-foreground` | `oklch(0.19 0.025 58)` / `var(--foreground)` | dialog surfaces |
  | `--primary-foreground` | `oklch(0.17 0.03 60)` | dark oak text on gold |
  | `--secondary` / `--secondary-foreground` | `oklch(0.24 0.03 58)` / `var(--foreground)` | = legacy `--bg-elev-2` |
  | `--surface-muted` → `--color-muted` | `oklch(0.24 0.03 58)` | **collision**, see below |
  | `--muted-foreground` | `var(--muted)` | the legacy dim-text value |
  | `--surface-accent` → `--color-accent` | `oklch(0.30 0.05 68)` | **collision**, gold-tinted hover |
  | `--accent-foreground` | `var(--foreground)` | |
  | `--destructive` | `oklch(0.64 0.2 25)` | = legacy `--danger` |
  | `--success` | `oklch(0.72 0.17 150)` | badge `success` (R10) |
  | `--warning` | `oklch(0.80 0.15 80)` | badge `warning` (R10) |
  | `--input` | `var(--border-token)` | |
  | `--ring` | `var(--glow)` | focus ring |
  | `--radius` | `0.5rem` | matches today's 8px corners |

  `@theme inline` gains `--color-<name>: var(--<name>)` for every row (plus
  `--radius-sm/md/lg/xl` as `calc(var(--radius) ± …)`, the shadcn convention).
- **Rationale**: `index.css` already defines `--muted` as the dim *text* colour and
  `--accent` as an alias of `--primary`, and `styles.css` uses both in dozens of rules.
  shadcn's `bg-muted` is a *surface* and `hover:bg-accent` is a *hover surface*; mapping
  them 1:1 would paint tan text-colour backgrounds. Grep confirms no TSX uses the
  Tailwind classes `bg-muted`, `text-muted`, `bg-accent`, `text-primary`, `bg-card` today,
  so re-pointing `--color-muted` and `--color-accent` at new surface variables breaks
  nothing, and the legacy variables keep their meaning for `styles.css`.
- **Alternatives considered**: renaming the legacy variables across `styles.css` (large
  diff, no user value); a second `:root` block in `styles.css` (two sources of truth,
  violates Principle I; `styles.css`'s own `:root` hex block is already dead because
  `index.css` loads after it).

## R3. Dialog/tab animations and reduced motion

- **Decision**: do not add `tw-animate-css`. Strip the animation utility classes
  (`data-[state=open]:animate-in`, `data-[state=closed]:animate-out`, `fade-in-0`,
  `fade-out-0`, `zoom-in-95`, `zoom-out-95`, `slide-in-from-*`, `duration-200`) from the
  generated `dialog.tsx` and `alert-dialog.tsx`. Dialogs appear and disappear instantly.
- **Rationale**: these utilities come from a package `shadcn init` would have added to
  the CSS and which this project never installed; without it the classes are inert. FR-014
  (respect reduced motion) is satisfied trivially when no motion is added; one fewer
  dependency (Principle III).
- **Alternatives considered**: adding `tw-animate-css` plus a `prefers-reduced-motion`
  override (extra dependency and rule for a 150 ms fade nobody asked for).

## R4. Confirmation dialog shape

- **Decision**: one controlled component `ConfirmDialog` in `src/components/ConfirmDialog.tsx`
  built on `AlertDialog`:

  ```ts
  interface ConfirmDialogProps {
    open: boolean;
    title: string;            // e.g. "Disable user?"
    description: string;      // names the item: "rudolf@example.com will no longer be able to sign in."
    confirmLabel: string;     // "Disable", "Delete", "Remove"
    busy?: boolean;           // request in flight: buttons disabled, close requests ignored
    onConfirm: () => void | Promise<void>;
    onCancel: () => void;
  }
  ```
  Each call site holds the pending item in state (`pendingDisable: AdminUser | null`,
  `pendingDelete: Conversation | null`, `pendingRemove: {kind:"friend"|"guild", …} | null`)
  and renders one `ConfirmDialog`. The confirm action is `variant="destructive"`.
- **Rationale**: four call sites, all "name the item, Cancel, destructive confirm"; a
  controlled component is the simplest DRY shape and keeps focus management inside Radix.
  Keeping the dialog open while `busy` implements the spec edge case "Escape during an
  in-flight delete". `Sidebar.onDelete` widens to `(id: string) => void | Promise<void>`
  so the sidebar can await `App.removeConversation` and only then close.
- **Alternatives considered**: a `useConfirm()` promise hook with a provider in
  `main.tsx` (more machinery for four sites); keeping `window.confirm` for the admin page
  (forbidden by FR-006).

## R5. Guide viewer as a real modal

- **Decision**: replace `.profile-overlay` + `.guide-view-panel` with `Dialog`
  (`open={viewing !== null}`, `onOpenChange={(o) => !o && setViewing(null)}`),
  `DialogContent className="max-h-[86vh] overflow-y-auto sm:max-w-3xl"`,
  `DialogHeader` with `DialogTitle` "{class} — {spec}" and `aria-describedby={undefined}`
  (no description). The provenance row, markdown body and sources list keep their
  existing classes (`.guide-view-meta`, `.guide-view-body`, `.guide-sources`).
- **Rationale**: Radix Dialog provides focus trap, Escape, overlay click, body scroll lock
  and focus return (FR-005) with no app code. The View button that opened it stays mounted
  during the fetch, so Radix restores focus to it on close. `viewing` is separate state from
  `items`, so the polling refresh never closes or re-renders the dialog content.
- **Alternatives considered**: patching the hand-built overlay with a focus trap (the
  bespoke code this feature removes).

## R6. Tabs that keep both panels mounted

- **Decision**: Radix `Tabs` controlled by the existing `tab` state
  (`value={tab} onValueChange={(v) => setTab(v as Tab)}`); `TabsList` with two
  `TabsTrigger`s; both `TabsContent` panels get `forceMount` and
  `className="data-[state=inactive]:hidden"`. `ClassGuidesTab` keeps `active={tab === "guides"}`.
- **Rationale**: Radix unmounts inactive content by default, which would reset the
  in-progress identity form (FR-007). With `forceMount` both render; the `data-state`
  attribute selector hides the inactive one. Arrow-key navigation and `aria-selected`
  come from Radix. The deferred first fetch (FR-008) is already keyed off `active`.
- **Alternatives considered**: keeping the hand-rolled `role="tablist"` buttons and adding
  key handlers (duplicates Radix); unmounting panels (loses state).

## R7. Native dropdowns

- **Decision**: `NativeSelect` / `NativeSelectOption` from the registry for the model
  picker, raid role, admin invite role and identity region. The shadcn `select` (custom
  pop-up) is not installed.
- **Rationale**: FR-003 and the clarification session: native keyboard and mobile behaviour,
  shared chrome. `NativeSelect` is a styled `<select>` with a chevron icon.
- **Alternatives considered**: shadcn `select` (explicit non-goal).

## R8. Button emphasis set

- **Decision**: edit the generated `buttonVariants` to exactly `default`, `secondary`,
  `ghost`, `destructive` and sizes `default`, `sm`, `icon`; delete `outline`, `link`,
  `lg`, `icon-sm`, `icon-lg`. Mapping of today's controls:

  | today | variant / size |
  |---|---|
  | `.new-chat`, auth/admin submit, `.composer-send`, `.profile-form button`, `.guide-btn` View/Generate/Retry | `default` |
  | `.profile-open`, header PDF/Admin/Sign out, `.download-pdf`, admin Resend/Enable/Reset link/Copy, `.guide-btn-ghost` Refresh, `.profile-back`, admin "Back to app" | `secondary` (`size="sm"` in table rows) |
  | `.conversation-delete` ✕, `.profile-remove` ✕, dialog close, alert dismiss | `ghost` + `size="icon"` |
  | admin Disable, Revoke; ConfirmDialog confirm | `destructive` (`size="sm"` in rows) |

  Link-shaped buttons use `<Button asChild variant="secondary"><Link …/></Button>`.
- **Rationale**: FR-002 fixes the emphasis set; trimming the cva makes the rule checkable
  by reading one file and removes dead variants (constitution: no dead code).
- **Alternatives considered**: keep all registry variants unused (dead code, rule not
  enforceable).

## R9. Composer

- **Decision**: `Textarea` (rows=2, same placeholder, same `onKeyDown`) + `Button`
  ("Send", `disabled={disabled || !text.trim()}`). The `.composer` flex wrapper and its
  backdrop rule stay; `.composer-input` and `.composer-send` rules are deleted.
- **Rationale**: FR-004 keeps every behaviour; only the chrome changes.

## R10. Badges: tones beyond the registry's four variants

- **Decision**: add `success` and `warning` variants to the generated `badge.tsx`
  (`bg-success/15 text-success border-success/40`, `bg-warning/15 text-warning
  border-warning/40`, matching the existing translucent pill look). Create
  `src/components/StatusBadge.tsx`:

  ```ts
  type Tone = "ok" | "pending" | "failed" | "warn" | "neutral";
  const TONE_VARIANT: Record<Tone, BadgeVariant> = { ok: "success", pending: "secondary", failed: "destructive", warn: "warning", neutral: "outline"… }
  export const GUIDE_TONE: Record<GuideStatus, Tone>      // ready→ok, pending→pending, failed→failed, none→neutral
  export const USER_TONE: Record<string, Tone>            // active→ok, disabled→failed
  export const INVITE_TONE: Record<string, Tone>          // open→pending, accepted→ok, revoked→neutral, expired→warn
  export function StatusBadge({ tone, title, children })
  ```
  The "May be out of date" guide badge is `tone="warn"`; the header's "fallback list" is
  `tone="warn"` with its existing `title` tooltip (FR-010).
- **Rationale**: US4 requires colours that distinguish active/disabled/pending and the
  guide statuses already use green/blue/red/amber; the registry's four variants cannot
  express success and warning. One place for the status→tone facts (Principle I).
- **Alternatives considered**: `className` overrides at each call site (repeated five
  times); a separate pill component (duplicates Badge).
- **Note**: because R8 trims Button but Badge keeps `outline`, the "neutral" tone uses
  Badge `outline`; this is a badge variant, not a button emphasis, so FR-002 is unaffected.

## R11. Error and notice strips

- **Decision**: `src/components/StatusAlert.tsx` wrapping `Alert`/`AlertDescription`:
  `{ tone: "error" | "notice"; children; onDismiss?: () => void }` → `variant="destructive"`
  for errors, `default` for notices, optional ghost icon `Button` ("Dismiss") on the right.
  Used by `AdminUsersPage` (dismissible), `CharactersTab`, `ClassGuidesTab`, and the
  `App` shell is *not* changed (its in-stream error rendering is part of the message list,
  FR-015). Auth pages show form-level errors with `FieldError` (R12).
- **Rationale**: today there are five different error styles (`.profile-error`,
  `.profile-notice`, admin red paragraph, auth red paragraph, header warning); US4 asks
  for one.

## R12. Forms, labels and the neutral/indigo retirement

- **Decision**: auth pages and the admin invite form use `Field` + `FieldLabel` + `Input`
  (ids via `useId()` or fixed ids so `htmlFor` works), `FieldError` under the form for the
  form-level message, `Button type="submit"` for submit. The "Show password" checkbox stays
  a native `<input type="checkbox">` inside a `Label` (not a text input, dropdown or
  button; FR-001 does not cover it; shadcn `checkbox` is not added, YAGNI). Page shells:
  `min-h-screen flex items-center justify-center bg-background text-foreground p-4`;
  card: `w-full max-w-sm space-y-4 rounded-2xl border border-border bg-card p-6`;
  secondary text `text-muted-foreground`; links `text-primary hover:text-glow`.
  Files: `LoginPage`, `AcceptInvitePage`, `ResetPasswordPage`, `ForbiddenPage`,
  `AdminUsersPage`, `auth/RequireAuth.tsx` (loading state).
- **Rationale**: FR-011 / SC-005; `grep -rnE 'neutral-|indigo-|red-[0-9]' src` must be
  empty afterwards and doubles as the acceptance check.

## R13. Dead CSS to remove from `styles.css`

- **Decision**: delete the rules that only styled replaced controls: `.new-chat`,
  `.conversation-delete`, `.model-select`, `.model-select-wrap`, `.model-degraded`,
  `.download-pdf`, `.bg-toggle*` (already unused), `.composer-input`, `.composer-send`,
  the transition/hover rules that list them, `.profile-open`, `.profile-overlay`,
  `.profile-panel`, `.profile-header`, `.profile-close`, `.profile-error`, `.profile-remove`,
  `.profile-form input/select/button`, `.guide-badge*`, `.guide-none`, `.guide-btn*`,
  `.guide-view-panel`, `.profile-tabs`, `.profile-tab*`, `.profile-notice`. Keep layout
  rules (`.sidebar`, `.conversation-item`, `.composer`, `.chat-header`, `.profile-page*`,
  `.profile-tabpanel`, `.profile-section`, `.profile-row`, `.profile-form` flex wrapper,
  `.guide-grid`, `.guide-class-*`, `.guide-spec-*`, `.guide-meta`, `.guide-view-*`,
  `.guide-sources`, `.profile-back` is replaced by a Button so its rules go too).
- **Rationale**: no dead code (constitution); each deletion is paired with the component
  swap that orphaned it so every slice stays buildable.

## R14. Verification approach

- **Decision**: no frontend test runner is added in this feature. Checks are:
  1. `tsc -b` and `vite build` succeed.
  2. Native-control audit: `grep -rnE '<(button|input|select|textarea)\b|confirm\(' src
     --include='*.tsx' --exclude-dir=ui` returns only the allowlist in
     `contracts/ui-components.md` (checkboxes, FR-015 elements).
  3. Palette audit: `grep -rnE 'neutral-|indigo-|red-[0-9]' src` is empty.
  4. Size gate: gzip of `dist/assets/index-*.js` (and total JS) after ≤ 1.10 × before.
  5. Manual keyboard/dialog checklist per story in `quickstart.md`.
- **Rationale**: the repo has no vitest/jsdom today; introducing one is a separate
  infrastructure decision that this feature does not need to ship, and the behaviours
  under test (focus trap, roving tabindex) are Radix's, not ours.
- **Alternatives considered**: adding vitest + Testing Library for `ConfirmDialog` and
  `ProfilePage` tabs (deferred; recommended as a follow-up once a second feature needs it).
