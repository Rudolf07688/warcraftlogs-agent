# Data Model: Shared UI Component Adoption

**Feature**: 010-shadcn-ui-adoption | **Date**: 2026-10-11

Frontend-only feature: no database, API or persisted shape changes. The "entities" are
UI state and lookup tables that cross component boundaries, typed as TypeScript interfaces
(the frontend analogue of the constitution's typed-contract rule).

## 1. ConfirmRequest (per call site, held in component state)

| Field | Type | Notes |
|---|---|---|
| `open` | `boolean` | derived: pending item !== null |
| `title` | `string` | "Disable user?", "Delete conversation?", "Remove friend?", "Remove guild?" |
| `description` | `string` | names the item (email, conversation title, `Name-Server (Region)`, `Guild-Server (Region)`) |
| `confirmLabel` | `string` | "Disable", "Delete", "Remove" |
| `busy` | `boolean` | request in flight; blocks close + disables both actions |

**State transitions**: `idle` → (click destructive control) → `pending` → (Cancel / Escape /
outside click, only when not busy) → `idle`; `pending` → (Confirm) → `busy` → (resolve) →
`idle` (+ list refresh) or (reject) → `idle` + `StatusAlert(error)`; the item stays unchanged.

**Owners**: `AdminUsersPage.pendingDisable: AdminUser | null`;
`Sidebar.pendingDelete: Conversation | null`;
`CharactersTab.pendingRemove: { kind: "friend"; friend: Character } | { kind: "guild"; guild: Guild } | null`.

## 2. Tone and status maps (`src/components/StatusBadge.tsx`)

```ts
export type Tone = "ok" | "pending" | "failed" | "warn" | "neutral";

const TONE_VARIANT: Record<Tone, "success" | "secondary" | "destructive" | "warning" | "outline">;

export const GUIDE_TONE:  Record<GuideStatus, Tone>; // ready→ok · pending→pending · failed→failed · none→neutral
export const USER_TONE:   Record<string, Tone>;      // active→ok · disabled→failed · (other)→neutral
export const INVITE_TONE: Record<string, Tone>;      // open→pending · accepted→ok · revoked→neutral · expired→warn
```

`GuideStatus` is the existing union in `src/types.ts`; `AdminUser.status` and
`Invitation.status` are plain strings in `types.ts` (server-defined), so their maps are
`Record<string, Tone>` with a `neutral` fallback.

Labels stay where they are today: `STATUS_LABEL` (CharactersTab) and `CHIP_LABEL`
(ClassGuidesTab) are both guide-status label maps and are **merged into one**
`GUIDE_LABEL` in `StatusBadge.tsx` (DRY), keeping each tab's wording as a parameter where
they differ ("guide ready" vs "Downloaded"): `GUIDE_LABEL_SHORT` (badge beside a
character) and `GUIDE_LABEL_LIBRARY` (roster chip).

## 3. StatusAlert props

```ts
interface StatusAlertProps {
  tone: "error" | "notice";
  children: ReactNode;
  onDismiss?: () => void;   // renders a ghost icon Button labelled "Dismiss"
  className?: string;
}
```

## 4. Theme token contract (`src/index.css`)

Source variables on `:root` and their `@theme inline` colour names. Existing rows are kept;
new rows are added by this feature.

| source variable | `@theme inline` name | status |
|---|---|---|
| `--background`, `--foreground`, `--card`, `--primary`, `--glow`, `--border-token` | `--color-background/foreground/card/primary/glow/border` | existing |
| `--muted` (dim text) | `--color-muted-foreground` | **re-mapped** (was `--color-muted`) |
| `--surface-muted` | `--color-muted` | new |
| `--surface-accent` | `--color-accent` | new |
| `--card-foreground`, `--popover`, `--popover-foreground`, `--primary-foreground`, `--secondary`, `--secondary-foreground`, `--accent-foreground`, `--destructive`, `--success`, `--warning`, `--input`, `--ring` | `--color-<same>` | new |
| `--radius` | `--radius-sm/md/lg/xl` | new |

Legacy aliases used by `styles.css` (`--bg`, `--bg-elev`, `--bg-elev-2`, `--border`,
`--text`, `--text-dim`, `--accent`, `--user`, `--agent`, `--danger`, `--wow-gold*`) are
unchanged.

## 5. Component prop changes (public surface inside the app)

| Component | Before | After |
|---|---|---|
| `Sidebar.onDelete` | `(id: string) => void` | `(id: string) => void \| Promise<void>` (awaited to keep the confirm dialog open while busy) |
| `ModelSelect` | unchanged props | unchanged |
| `Composer` | unchanged | unchanged |
| `ClassGuidesTab({ active })` | unchanged | unchanged |
| `CharactersTab()` | unchanged | unchanged |

No other prop, route or API client signature changes.
