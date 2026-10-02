// Typed localStorage-backed UI preferences for the resizable side panel. All reads
// are defensive: corrupt or out-of-range values fall back to the default rather than
// throwing. (The Phase-2 background preference was removed in US6 — one fixed theme.)

export const SIDEBAR_MIN = 200;
export const SIDEBAR_MAX = 480;
export const SIDEBAR_DEFAULT = 260;

const SIDEBAR_KEY = "wcl.ui.sidebarWidth";

export function clampSidebarWidth(px: number): number {
  if (!Number.isFinite(px)) return SIDEBAR_DEFAULT;
  return Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, Math.round(px)));
}

export function getSidebarWidth(): number {
  try {
    const raw = localStorage.getItem(SIDEBAR_KEY);
    if (raw == null) return SIDEBAR_DEFAULT;
    return clampSidebarWidth(Number(raw));
  } catch {
    return SIDEBAR_DEFAULT;
  }
}

export function setSidebarWidth(px: number): void {
  try {
    localStorage.setItem(SIDEBAR_KEY, String(clampSidebarWidth(px)));
  } catch {
    // Ignore storage failures (private mode, quota) — preference is non-critical.
  }
}
