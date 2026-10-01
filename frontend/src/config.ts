// US6: selectable app backgrounds. The new image is the default; the previous
// background is retained, plus a solid-color option. Assets are served from
// `frontend/public/assets/` (Vite serves `public/` at the site root), so adding a
// new background means dropping the file there — e.g.
// `frontend/public/assets/background_2.jpg`.
//
// If a configured image is missing or fails to load, the layered body background
// falls back to the solid `--bg` color (see styles.css), so nothing breaks.

export interface BackgroundOption {
  id: string; // stable key persisted in localStorage (wcl.ui.background)
  label: string; // shown in the toggle
  src: string; // public URL, or "" for the solid color
  default?: boolean;
}

export const BACKGROUNDS: BackgroundOption[] = [
  {
    id: "background-2",
    label: "Tavern",
    src: "/assets/background_2.jpg",
    default: true,
  },
  { id: "classic", label: "Classic", src: "/assets/background.webp" },
  { id: "none", label: "Solid color", src: "" },
];

export const DEFAULT_BACKGROUND_ID =
  BACKGROUNDS.find((b) => b.default)?.id ?? BACKGROUNDS[0].id;

export function resolveBackground(id: string): BackgroundOption {
  return BACKGROUNDS.find((b) => b.id === id) ?? BACKGROUNDS[0];
}

/** CSS value for `--bg-image`: a url() for image options, or `none` for solid. */
export function backgroundCssValue(id: string): string {
  const src = resolveBackground(id).src;
  return src ? `url("${src}")` : "none";
}
