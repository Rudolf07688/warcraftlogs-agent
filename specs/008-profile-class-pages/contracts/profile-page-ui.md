# Contract: Profile page UI (US1) + Class Guides tab (US2)

Frontend contract for the dedicated, themed, tabbed profile page. Desktop-primary.

## Routing (`frontend/src/main.tsx`)

- Add a guarded top-level route (mirroring `/admin/users`):
  ```tsx
  { path: "/profile", element: <RequireAuth><ProfilePage /></RequireAuth> }
  ```
- `App.tsx`: the former "open profile" control navigates to `/profile` (`useNavigate`); the `ProfilePanel` modal is removed. The profile page provides a clear way back to the chat (`/app`).

## `ProfilePage.tsx` (NEW)

- Themed page shell (Warcraft styling) with a **tab bar**: `Characters` (default) and `Class Guides`. Tab state is local; switching tabs preserves each tab's in-progress input (FR-002).

### Characters tab (`components/profile/CharactersTab.tsx`, extracted from `ProfilePanel`)
- Reuses existing REST calls (`getProfile`, `putSelf`, `addFriend`, `updateFriend`, `deleteFriend`, `putGuild`, `deleteGuild`).
- Sections: **You** (self), **Friends** (unlimited; add form; per-row raid-role control inferred-vs-set, from feature 007; friendly `409 duplicate_friend` → "already added"), **Main guild**.
- Per-character guide badge reads the derived `guide_status` from `CharacterOut` (unchanged shape).
- Restyled with themed buttons/inputs/selects/cards (FR-005); all prior behavior preserved (FR-003, FR-004).

### Class Guides tab (`components/profile/ClassGuidesTab.tsx`, NEW)
- On mount: `GET /api/guides` → render the **full roster** grouped by class, each spec row showing a status chip: `Downloaded` (ready), `Generating…` (pending), `Failed` (failed), `Not downloaded` (none) (FR-008, SC-002).
- Per spec actions:
  - `Generate` when `none`; `Retry` when `failed`; `Refresh` when `ready` (sends `force: true`) → `POST /api/guides/{class}/{spec}/generate`.
  - `View` when `ready` → fetch `GET /api/guides/{class}/{spec}` and render `guide_markdown` via the existing `StreamMarkdown` (no second renderer; Principle I).
- While any spec is `pending`, poll `GET /api/guides` on an interval (reusing the ProfilePanel polling idiom) until none remain pending.
- `429 rate_limited` → show the "slow down" message with the retry hint (FR-014); failures are retryable (no permanent stuck state; FR-010/FR-011).

## REST client (`frontend/src/api/restClient.ts`, EDIT)
```ts
export async function listGuides(): Promise<GuideListOut>
export async function getGuide(className: string, spec: string): Promise<GuideOut>
export async function generateGuide(className: string, spec: string, force?: boolean): Promise<GuideOut>  // POST, csrf
```

## Types (`frontend/src/types.ts`, EDIT)
```ts
export type GuideStatus = "none" | "pending" | "ready" | "failed";
export interface GuideListItem { class_name: string; class_display: string; spec: string; status: GuideStatus; updated_at: string | null; }
export interface GuideListOut { guides: GuideListItem[]; }
export interface Guide { class_name: string; spec: string; status: GuideStatus; guide_markdown: string | null; updated_at: string | null; }
```

## Theming (`styles.css` / `index.css`, EDIT)
- Add Warcraft-themed tokens/classes (consistent palette, panel/card framing, button/tab styles) applied across the page, the tabs, and both tabs' controls (FR-005, SC-007). Keyboard-operable and labeled controls.

## Acceptance mapping
- FR-001 dedicated route; FR-002 tabs; FR-003/FR-004 preserved profile behavior; FR-005 theme; FR-008/FR-012 class guides list + view; FR-009/FR-010 generate/retry/refresh; FR-014 rate-limit feedback; SC-001 one-click reach + full action parity; SC-002 full roster; SC-007 clarity + a11y.
