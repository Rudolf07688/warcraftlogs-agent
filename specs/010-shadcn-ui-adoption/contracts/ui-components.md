# Contract: Shared UI Components, Tokens, Accessible Names, Audit Allowlist

**Feature**: 010-shadcn-ui-adoption | **Date**: 2026-10-11

This is a frontend-only feature; there is no HTTP or WebSocket contract change. The
contracts below are what the rest of the app (and the audit checks) may rely on.

## 1. Generated primitives (`frontend/src/components/ui/`)

| File | Exports used by the app | Local edits allowed |
|---|---|---|
| `button.tsx` | `Button`, `buttonVariants` | variants trimmed to `default`, `secondary`, `ghost`, `destructive`; sizes `default`, `sm`, `icon` |
| `input.tsx` | `Input` | none |
| `textarea.tsx` | `Textarea` | none |
| `label.tsx` | `Label` | none |
| `field.tsx` | `Field`, `FieldLabel`, `FieldError`, `FieldDescription` (others may stay unused) | none |
| `native-select.tsx` | `NativeSelect`, `NativeSelectOption` | lucide→react-icons if the CLI left any |
| `dialog.tsx` | `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogClose` | animation classes removed; lucide→react-icons |
| `alert-dialog.tsx` | `AlertDialog`, `AlertDialogContent`, `AlertDialogHeader`, `AlertDialogTitle`, `AlertDialogDescription`, `AlertDialogFooter`, `AlertDialogCancel`, `AlertDialogAction` | animation classes removed |
| `tabs.tsx` | `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent` | none |
| `table.tsx` | `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell` | none |
| `badge.tsx` | `Badge`, `badgeVariants` | + `success`, `warning` variants |
| `alert.tsx` | `Alert`, `AlertTitle`, `AlertDescription` | none |
| `separator.tsx` | (none directly; imported by `field.tsx`) | none |
| `card.tsx` | `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardAction`, `CardContent`, `CardFooter` (profile revamp) | none |
| `item.tsx` | `Item`, `ItemGroup`, `ItemMedia`, `ItemContent`, `ItemTitle`, `ItemDescription`, `ItemActions` (profile revamp) | none |
| `empty.tsx` | `Empty`, `EmptyHeader`, `EmptyMedia`, `EmptyTitle`, `EmptyDescription`, `EmptyContent` (profile revamp) | none |
| `avatar.tsx` | `Avatar`, `AvatarFallback` (profile revamp) | none |
| `toggle.tsx` / `toggle-group.tsx` | `ToggleGroup`, `ToggleGroupItem` (profile revamp) | none |
| `skeleton.tsx` | `Skeleton` (profile revamp) | none |
| `spinner.tsx` | `Spinner` (profile revamp) | lucide `Loader2Icon` → `LuLoaderCircle` |
| `input-group.tsx` | `InputGroup`, `InputGroupInput`, `InputGroupAddon` (profile revamp) | none |

All files: imports rewritten from the CLI's `"cn"` / `"src/components/ui/…"` to `"../../lib/utils"` / `"./…"` (the CLI mis-resolved the aliases, research R1). `alert-dialog.tsx` / `dialog.tsx`: `variant="outline"` defaults changed to `secondary` because `outline` was trimmed from Button.

Rule: nothing outside `ui/` styles a text input, dropdown, textarea or button with its own
CSS class or Tailwind string; it imports from `ui/` or from the wrappers below.

## 2. App wrappers (`frontend/src/components/`)

```ts
// ConfirmDialog.tsx
export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
}
export function ConfirmDialog(props: ConfirmDialogProps): JSX.Element;
// Behaviour: Cancel/Escape/outside click → onCancel, ignored while busy. Confirm button is
// variant="destructive". Focus starts on Cancel (AlertDialog default) and returns to the
// opener on close.

// StatusAlert.tsx
export interface StatusAlertProps {
  tone: "error" | "notice";
  children: React.ReactNode;
  onDismiss?: () => void;
  className?: string;
}
export function StatusAlert(props: StatusAlertProps): JSX.Element;
// error → role="alert" (Alert default), variant destructive; notice → variant default.

// StatusBadge.tsx
export type Tone = "ok" | "pending" | "failed" | "warn" | "neutral";
export const GUIDE_TONE: Record<GuideStatus, Tone>;
export const USER_TONE: Record<string, Tone>;
export const INVITE_TONE: Record<string, Tone>;
export const GUIDE_LABEL_SHORT: Record<GuideStatus, string>;   // "", "guide loading…", "guide ready", "guide unavailable"
export const GUIDE_LABEL_LIBRARY: Record<GuideStatus, string>; // "Not downloaded", "Generating…", "Downloaded", "Failed"
export function StatusBadge(props: { tone: Tone; title?: string; children: React.ReactNode }): JSX.Element;
```

## 3. Theme tokens (`frontend/src/index.css`)

New `:root` variables: `--card-foreground`, `--popover`, `--popover-foreground`,
`--primary-foreground`, `--secondary`, `--secondary-foreground`, `--surface-muted`,
`--muted-foreground`, `--surface-accent`, `--accent-foreground`, `--destructive`,
`--success`, `--warning`, `--input`, `--ring`, `--radius`.

`@theme inline` must expose, at minimum: `--color-background`, `--color-foreground`,
`--color-card`, `--color-card-foreground`, `--color-popover`, `--color-popover-foreground`,
`--color-primary`, `--color-primary-foreground`, `--color-secondary`,
`--color-secondary-foreground`, `--color-muted`, `--color-muted-foreground`,
`--color-accent`, `--color-accent-foreground`, `--color-destructive`, `--color-success`,
`--color-warning`, `--color-border`, `--color-input`, `--color-ring`, `--color-glow`,
`--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-xl`.

Legacy variables consumed by `styles.css` keep their names and meanings.

## 4. Accessible-name register (FR-013): names that must survive the swap

| Screen | Control | Name today | Mechanism after |
|---|---|---|---|
| Chat header | model picker | `title="Model"` | `aria-label="Model"` on `NativeSelect` (also keep `title`) |
| Chat header | fallback warning | `title="Model discovery could not reach Vertex; showing a fallback list."` | same `title` on `StatusBadge` |
| Chat header | PDF | `title="Download this conversation as a PDF report"` | same |
| Chat header | Admin link | `title="Manage users & invitations"` | same |
| Chat header | Sign out | `title="Sign out"` | same |
| Sidebar | Profile | `title="Edit your profile"` | same |
| Sidebar | delete conversation | `title="Delete"` | `aria-label="Delete conversation"` + `title="Delete"` |
| Sidebar | raid item | `title="Investigate {label}"` | unchanged (FR-015) |
| Profile | raid role select | `aria-label="Raid role"` | same |
| Profile (revamp) | self raid role | — | `ToggleGroup aria-label="Raid role"`; friend rows keep the select |
| Profile (revamp) | identity dialog fields | `aria-label` Name / Server / Region | visible `FieldLabel`s Name / Server / Region |
| Profile (revamp) | add friend | button text "Add friend" | same text, opens the identity dialog |
| Class Guides (revamp) | search | — | `aria-label="Search classes and specs"` |
| Class Guides (revamp) | status filter | — | `ToggleGroup aria-label="Filter by status"` |
| Class Guides (revamp) | refresh | button text "Refresh" | icon button, `aria-label="Refresh {spec} {class} guide"` + `title="Regenerate this guide"` |
| Profile | remove friend / guild | `title="Remove friend"` / `title="Remove guild"` | same + `aria-label` |
| Profile tabs | tablist | `aria-label="Profile sections"` | same on `TabsList` |
| Class Guides | refresh | `title="Regenerate this guide"` | same |
| Class Guides | provenance | `title="Patch the guide targets · when it was generated"` | unchanged |
| Class Guides | stale badge | freshness-specific `title` | same on `StatusBadge` |
| Guide dialog | dialog | `aria-label="{class} {spec} guide"` | `DialogTitle` "{class} — {spec}" (labelled-by); revamp: "{spec} {class}" + provenance as `DialogDescription` |
| Guide dialog | close | `title="Close"` | `DialogClose` with visually hidden "Close" text |
| Admin | status alert | (none) | `role="alert"` from `Alert` |
| Composer | textarea | placeholder only | add `aria-label="Message"` |

## 5. Native-control audit (SC-001, SC-002)

Command (from `frontend/`):

```sh
grep -rnE '<(button|input|select|textarea)\b|confirm\(' src --include='*.tsx' --exclude-dir=ui
```

Allowed matches after implementation (everything else is a defect):

| File | Element | Reason |
|---|---|---|
| `pages/LoginPage.tsx`, `pages/AcceptInvitePage.tsx`, `pages/ResetPasswordPage.tsx` | `<input type="checkbox">` (Show password) | checkbox, outside FR-001's set (research R12) |
| `components/EncounterPicker.tsx` | `<input type="checkbox">` chips | boss-focus picker, unchanged (FR-015) |
| `components/FollowUps.tsx` | `<button>` chips | follow-up chips, unchanged (FR-015) |
| `components/Sidebar.tsx` | `<button className="sidebar-section-label">` ×2, `<button className="raid-item">` | collapsible sections + raid items, unchanged (FR-015) |
| `components/MessageList.tsx`, `components/SpellCard.tsx` | `<button>` back-to-bottom, spellbook toggle, per-message download | message renderer, unchanged (FR-015) |
| `components/BackendBootGate.tsx` | any | boot overlay, unchanged (FR-015) |

`confirm(` must have zero matches.

## 6. Palette audit (SC-005)

```sh
grep -rnE 'neutral-|indigo-|red-[0-9]' src
```

Must return nothing.

## 7. Size gate (SC-006)

```sh
npm run build && gzip -c dist/assets/index-*.js | wc -c
```

Record the number before the first change and after the last; after ≤ 1.10 × before.
