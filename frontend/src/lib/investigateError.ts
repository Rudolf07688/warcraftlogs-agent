/**
 * The message for a failed "investigate this raid" click (052 QA BUG-004). The server limits
 * investigations per user (429 rate_limited, Retry-After 60): say so instead of suggesting the
 * backend is down, which only invites another click.
 */
export function investigateErrorMessage(err: unknown): string {
  const status = (err as { status?: unknown } | null)?.status;
  return status === 429
    ? "Too many investigations in the last minute. Wait a minute, then try again."
    : "Could not start the investigation. Is the backend up?";
}
