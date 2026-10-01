# UI Configuration & Preference Contract — 003-chat-followups-ux

Frontend-only contracts for the resizable side panel (US5) and togglable background
(US6). No backend endpoints are added; preferences live in `localStorage`.

## Background configuration (`frontend/src/config.ts`)

```ts
export interface BackgroundOption {
  id: string;        // stable key persisted in localStorage
  label: string;     // shown in the toggle UI
  src: string;       // asset URL from SOURCE assets (not dist/); "" = solid color
  default?: boolean; // exactly one option is the default
}

export const BACKGROUNDS: BackgroundOption[] = [
  { id: "morgan-howell-1760", label: "Morgan Howell",
    src: new URL("./assets/morgan-howell-img-1760.jpg", import.meta.url).href,
    default: true },
  { id: "classic", label: "Classic", src: "/* previous background */" },
  { id: "none", label: "Solid color", src: "" },
];
```

Rules:
- Exactly one option has `default: true` and it MUST be the new Morgan Howell image (FR-019).
- The previous background MUST remain selectable (FR-020).
- The rendered background MUST include a dark scrim/overlay so chat text stays legible over
  any image (FR-021).
- If the chosen image fails to load, fall back to the solid `--bg` color (FR-021).

## UI preferences (`localStorage`)

| Key | Type | Default | Constraint |
|-----|------|---------|------------|
| `wcl.ui.sidebarWidth` | number (px, serialized) | 260 | clamped to `[SIDEBAR_MIN=200, SIDEBAR_MAX=480]` on read and write (FR-018) |
| `wcl.ui.background` | string (BackgroundOption id) | the default option's id | must match a known `BACKGROUNDS[].id`; unknown values fall back to default |

Rules:
- `sidebarWidth` is restored on load and re-applied to the `--sidebar-width` CSS variable
  (FR-016/017); out-of-range or corrupt values are clamped/ignored.
- `background` selection is restored on load (FR-020); an unknown id resolves to the
  default (FR-019).

## CSS contract

- `.app` grid column changes from fixed `260px` to `var(--sidebar-width, 260px) 1fr`.
- A resizer element sits on the sidebar/main boundary; dragging it updates
  `--sidebar-width` within the clamp. The handle MUST remain reachable at the minimum width.
- `.message` / `.message.agent` max-width becomes responsive (e.g. `min(860px, 100%)`), so
  response panels size to content and available width instead of a fixed pixel cap (US3).
- Body/app background is driven by the selected `BackgroundOption.src` plus a legibility
  scrim; `src === ""` uses the solid `--bg`.
