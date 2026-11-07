// Feature 074: where the app sends a player after activating an account or signing in. Only
// fixed paths, or an in-app path that can't leave the origin, are ever navigated to.

export const CHAT_HOME = "/app";
export const PROFILE_PATH = "/profile";

/**
 * `path` if it is an in-app path, else the chat home. Rejects anything that isn't a plain
 * absolute path: `//host` and `/\host` (browsers read both as another origin), schemes like
 * `javascript:`, and control characters (which browsers strip before parsing).
 */
export function safeInternalPath(path: unknown): string {
  if (typeof path !== "string" || !path.startsWith("/")) return CHAT_HOME;
  if (path.startsWith("//") || path.includes("\\")) return CHAT_HOME;
  if (/[\u0000-\u001f\u007f]/.test(path)) return CHAT_HOME;
  return path;
}

/** The sign-in target: the profile page while onboarding is pending and the player was headed home. */
export function afterLoginPath(from: unknown, onboardingPending: boolean): string {
  const target = safeInternalPath(from);
  const home = target === CHAT_HOME || target === `${CHAT_HOME}/`;
  return home && onboardingPending ? PROFILE_PATH : target;
}
