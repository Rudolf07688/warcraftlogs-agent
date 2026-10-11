# Implementation Plan: Shared UI Component Adoption

**Branch**: `010-shadcn-ui-adoption` | **Date**: 2026-10-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/010-shadcn-ui-adoption/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

The frontend has shadcn/ui configured (`components.json`, `cn()` helper, Tailwind v4,
`react-icons` as the icon library) but no component has ever been added. This update
installs twelve registry components into `src/components/ui/`, extends the existing
Tavern Hearth theme in `index.css` with the token names those components read, and
replaces every hand-styled text input, dropdown, label, validation message, button,
tab strip, table, badge, alert and modal on the auth, admin, profile and chat-shell
screens with the shared equivalents. Two thin app-level wrappers (`ConfirmDialog` on
AlertDialog, `StatusAlert` on Alert) give the four irreversible deletes one confirmation
flow and the pages one error/notice strip. The auth, admin and forbidden pages drop the
Tailwind `neutral-*`/`indigo-*` utilities for theme tokens so the whole app shares the
dark-gold palette. Frontend only: no backend, schema or endpoint change.

## Technical Context

**Language/Version**: TypeScript 5.5 / React 19.3 (Vite 5, Tailwind CSS 4.3 via `@tailwindcss/vite`)

**Primary Dependencies**: shadcn/ui registry components (new-york style, `cssVariables: true`), `radix-ui` (unified package; the only new runtime dependency — Dialog, AlertDialog, Tabs, Label, Slot), `class-variance-authority` 0.7, `clsx`, `tailwind-merge` (already installed), `react-icons` 5.7 (already installed; shadcn CLI maps lucide icons to it because `iconLibrary` is `react-icons`), `react-router-dom` 7

**Storage**: N/A (no persistence change; the sidebar width in `localStorage` is untouched)

**Testing**: `tsc -b` (strict) and `vite build` are the only automated frontend checks in the repo today; there is no test runner. This feature adds (a) a grep-based native-control audit documented in `contracts/ui-components.md` (SC-001/SC-002), (b) a before/after `vite build` gzip-size comparison (SC-006), and (c) a manual keyboard/dialog checklist in `quickstart.md` (SC-003/SC-004). The backend suite (`uv run pytest`) is unaffected but is still run before commit.

**Target Platform**: evergreen desktop and mobile browsers; served by the Vite dev server in docker compose (`frontend` service) and by `vite build` output

**Project Type**: web application (FastAPI backend + ADK agent + React frontend); this feature touches `frontend/` only

**Performance Goals**: no perceptible change; initial JS download (gzip) grows ≤ 10% over the current build (SC-006); dialogs open and close without animation delay

**Constraints**: keep every existing accessible name/role (FR-013); native `<select>` behaviour kept (FR-003); no second icon library (FR-012); no animation that ignores reduced-motion (FR-014); the themed chat elements listed in FR-015 are not edited; `components.json` aliases are kept so later `shadcn add` calls land in the same places

**Scale/Scope**: 12 generated component files, 2 new wrapper components, 1 new badge helper; 13 existing files edited (`index.css`, `styles.css`, 6 pages/guards, `ModelSelect`, `Composer`, `Sidebar`, `CharactersTab`, `ClassGuidesTab`, `App.tsx` header); ~1,300 lines of `styles.css` of which ~180 lines of now-dead rules are removed

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|---|---|---|
| I. Strict DRY & Reuse-First | PASS | One source per control: `ui/button.tsx` replaces nine ad-hoc button styles (`.new-chat`, `.profile-open`, `.download-pdf`, `.composer-send`, `.guide-btn`, `.profile-form button`, `.profile-remove`, `.profile-close`, admin Tailwind strings). One `ConfirmDialog` for four deletes; one `StatusAlert` for every error/notice strip (today five different styles); one `StatusBadge` + tone maps for guide/user/invitation statuses. Reuses the existing `cn()` helper, `components.json`, `react-icons`, theme tokens in `index.css`. |
| II. Methodical, Step-Wise Delivery | PASS | Slices in spec priority order, each leaving the app building and usable: (0) install + tokens, (1) US1 forms/buttons per screen, (2) US2 guide dialog + confirmations, (3) US3 tabs, (4) US4 tables/badges/alerts, (5) dead-CSS removal + audit + size check. Each slice ends with `tsc -b`, `vite build` and the quickstart checks for that story. |
| III. Simplicity First (YAGNI) | PASS | One new package (`radix-ui`), justified below. No form library, no state manager, no toast system, no custom select, no animation library (`tw-animate-css` deliberately not added, research R3). Generated components are kept as generated except for three recorded edits (research R3, R8, R10). |
| IV. Typed Data Contracts | PASS (frontend scope) | Component props are explicit TypeScript interfaces (`ConfirmDialogProps`, `StatusAlertProps`, `StatusBadgeProps`); badge tone maps are typed `Record<Status, Tone>`; no `any`. Pydantic/dataclass rules apply to Python, which this feature does not touch. |
| V. Async Python Backend | N/A | No backend change. |
| VI. Repo Awareness via GitNexus | PASS | `impact --direction upstream` run during planning: `ModelSelect`, `Composer`, `Sidebar` → LOW (one caller `App`, 3 processes); `ClassGuidesTab`, `CharactersTab` → LOW (one caller `ProfilePage`, 6 processes); `AdminUsersPage` → UNKNOWN (no resolvable callers) confirmed by text search: referenced only as a route element in `main.tsx`, as are `LoginPage`, `AcceptInvitePage`, `ResetPasswordPage`, `ForbiddenPage`, `ProfilePage`. All component prop contracts stay the same except `Sidebar.onDelete`, which widens to `(id) => void \| Promise<void>` (additive). Re-run `impact` before each edit and `detect_changes` before each commit. |

**Complexity Tracking** (one entry, see table at the end): the `radix-ui` dependency.

**Post-design re-check (Phase 1)**: all PASS, unchanged. Design added two app wrappers
(`ConfirmDialog`, `StatusAlert`) and one helper (`StatusBadge`); each exists because the
same markup would otherwise appear in three or more places (Principle I).

## Project Structure

### Documentation (this feature)

```text
specs/010-shadcn-ui-adoption/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0: R1–R14 decisions
├── data-model.md        # Phase 1: UI state entities, tone maps, token contract
├── quickstart.md        # Phase 1: install, run, per-story verification, audit, size gate
├── contracts/
│   └── ui-components.md # component inventory, variants, wrapper props, token names,
│                        #   accessible-name register, native-control allowlist
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
frontend/
├── components.json              # unchanged (aliases, new-york, react-icons)
├── package.json                 # + radix-ui (added by `shadcn add`)
└── src/
    ├── index.css                # + shared-component tokens (research R2); @theme inline
    │                            #   gains --color-* for every token the components read
    ├── styles.css               # − dead rules for replaced controls (list in R13)
    ├── components/
    │   ├── ui/                  # NEW, generated by `npx shadcn@latest add …`
    │   │   ├── button.tsx       #   variants trimmed to default|secondary|ghost|destructive (R8)
    │   │   ├── input.tsx
    │   │   ├── textarea.tsx
    │   │   ├── label.tsx
    │   │   ├── field.tsx
    │   │   ├── native-select.tsx
    │   │   ├── dialog.tsx       #   animation utility classes removed (R3)
    │   │   ├── alert-dialog.tsx #   animation utility classes removed (R3)
    │   │   ├── tabs.tsx
    │   │   ├── table.tsx
    │   │   ├── badge.tsx        #   + success | warning variants (R10)
    │   │   └── alert.tsx
    │   ├── ConfirmDialog.tsx    # NEW: controlled AlertDialog wrapper (R4)
    │   ├── StatusAlert.tsx      # NEW: Alert wrapper with tone + optional dismiss (R11)
    │   ├── StatusBadge.tsx      # NEW: Badge wrapper with tone + GUIDE/USER/INVITE maps (R10)
    │   ├── ModelSelect.tsx      # NativeSelect + StatusBadge(warning) for "fallback list"
    │   ├── Composer.tsx         # Textarea + Button
    │   ├── Sidebar.tsx          # Button (new chat, profile, delete) + ConfirmDialog
    │   └── profile/
    │       ├── CharactersTab.tsx  # Input/NativeSelect/Button/StatusBadge/StatusAlert/ConfirmDialog
    │       └── ClassGuidesTab.tsx # Button/StatusBadge/StatusAlert + Dialog guide viewer
    ├── pages/
    │   ├── LoginPage.tsx          # Field/Label/Input/Button, theme tokens
    │   ├── AcceptInvitePage.tsx   # same
    │   ├── ResetPasswordPage.tsx  # same
    │   ├── ForbiddenPage.tsx      # theme tokens only
    │   ├── AdminUsersPage.tsx     # Field/Input/NativeSelect/Button/Table/StatusBadge/
    │   │                          #   StatusAlert/ConfirmDialog, theme tokens
    │   └── ProfilePage.tsx        # Tabs (controlled, forceMount) + Button asChild back link
    ├── auth/RequireAuth.tsx       # loading state uses theme tokens
    └── App.tsx                    # header: Button (PDF, Admin asChild, Sign out)
```

**Structure Decision**: existing web-application layout. Generated primitives live under
`src/components/ui/` exactly where `components.json` points, so future `shadcn add`
calls need no configuration. App-specific wrappers sit beside the other components in
`src/components/`, not in `ui/`, so the `ui/` directory stays "generated, minimally
edited" and the three recorded edits are easy to re-apply after a registry update.

## Design Notes (from research)

1. **Install** (R1): `npx shadcn@latest add button input textarea label field
   native-select dialog alert-dialog tabs table badge alert` from `frontend/`. The CLI
   adds `radix-ui` to `package.json` and rewrites lucide icon imports to `react-icons`.
   After the add, grep `src/components/ui` for `lucide-react`; any survivor is replaced
   with the `react-icons/lu` equivalent (FR-012).
2. **Tokens** (R2): `index.css` gains the shadcn-named variables the components read.
   Two names collide with the legacy palette and are handled explicitly: the legacy
   `--muted` is a dim *text* colour and the legacy `--accent` equals `--primary`, both
   used by many `styles.css` rules. They keep their meaning; the Tailwind-facing
   `--color-muted` is re-pointed at a new surface variable and `--color-accent` at a
   new hover-surface variable (no TSX uses `bg-muted`/`text-muted`/`bg-accent` today,
   verified by grep), and `--muted-foreground` is mapped to the legacy `--muted` value.
3. **No animation library** (R3): the generated dialog/alert-dialog classes reference
   `tw-animate-css` utilities (`animate-in`, `fade-in-0`, `zoom-in-95`, …). They are
   removed from the generated files instead of adding the package; dialogs open and
   close instantly, which satisfies FR-014 without a reduced-motion rule.
4. **Confirmations** (R4): one controlled `ConfirmDialog` built on AlertDialog. While
   `busy`, Cancel/Confirm are disabled and close requests (Escape, outside click) are
   ignored, so an in-flight delete keeps the dialog open until it resolves (spec edge
   case). Call sites hold a `pending` item in state: `AdminUsersPage` (disable user),
   `Sidebar` (delete conversation), `CharactersTab` (remove friend, remove guild).
   Revoke invitation and re-enable user stay immediate (FR-006).
5. **Guide viewer** (R5): Radix `Dialog` with `DialogTitle` = "Class — Spec"; the
   content panel is `max-h-[86vh] overflow-y-auto sm:max-w-3xl`. Radix supplies focus
   trap, Escape, outside-click close, body scroll lock and focus return to the View
   button. The `viewing` state is independent of the list, so a background refresh
   does not disturb an open dialog.
6. **Tabs** (R6): Radix `Tabs` controlled by the existing `tab` state. Both
   `TabsContent` panels use `forceMount` plus `className="data-[state=inactive]:hidden"`
   so both stay mounted (state preserved, FR-007) while only one is visible; the
   `ClassGuidesTab active` prop is unchanged so the first guide fetch is still deferred
   (FR-008). Arrow keys and `aria-selected` come from Radix.
7. **Dropdowns** (R7): `NativeSelect` everywhere a `<select>` exists (model picker, raid
   role, admin invite role, identity region). Native element, shared chrome (FR-003).
8. **Buttons** (R8): `buttonVariants` trimmed to the spec's four emphases
   (`default`=primary, `secondary`, `ghost`, `destructive`) and three sizes
   (`default`, `sm`, `icon`); `outline` and `link` are deleted so the FR-002 rule is
   enforceable by reading one file. Links that look like buttons (`Back to chat`,
   `Back to app`, header `Admin`) use `<Button asChild variant="secondary">`.
9. **Badges and alerts** (R10, R11): `badge.tsx` gains `success` and `warning`
   variants backed by new `--success`/`--warning` tokens; `StatusBadge` maps the three
   status enums to tones in one module. `StatusAlert` wraps `Alert` with
   `tone: "error" | "notice"` and an optional dismiss button (ghost icon Button).
10. **Palette retirement** (R12): on the six neutral/indigo files, utilities map
    `bg-neutral-950`→`bg-background`, `bg-neutral-900/80`→`bg-card border border-border`,
    `text-neutral-400`→`text-muted-foreground`, `text-indigo-400`→`text-primary`,
    red error paragraphs→`FieldError`/`StatusAlert`. The grep `neutral-|indigo-|red-[0-9]`
    must return nothing under `src/` when done (SC-005).
11. **Verification without a test runner** (R14): the native-control audit grep and its
    allowlist (checkboxes, FR-015 elements) live in the contract; the gzip size gate
    compares `vite build` output before and after; keyboard/dialog behaviour is checked
    by the quickstart checklist. Adding a frontend test runner was considered and
    deferred (research R14).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New runtime dependency `radix-ui` | FR-005 (focus trap, scroll lock, focus return, Escape) and FR-007 (roving-tabindex tabs with `aria-selected`) are exactly the behaviours the hand-built overlay and tab strip get wrong today; Radix is the headless layer every shadcn dialog/tab/label component is generated against. | Hand-writing a focus trap, scroll lock and roving tabindex in the app duplicates well-tested behaviour and is the kind of bespoke code this feature exists to remove; the previous attempt (`.profile-overlay`) already shows the failure mode. |
