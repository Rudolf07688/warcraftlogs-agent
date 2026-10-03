import { useEffect, useRef, useState } from "react";
import { acceptInvitation, ApiError } from "../api/restClient";

/**
 * Invitation acceptance (feature 006, US1).
 *
 * Reads the single-use token from the URL fragment (`#token=…`), immediately strips it
 * from the address bar via history.replaceState (so a reload can't re-submit it and it
 * never lands in history), and keeps it only in memory. Collects a first password and
 * activates the account. `Referrer-Policy: no-referrer` keeps the fragment out of any
 * outbound Referer (research R9).
 */
export default function AcceptInvitePage() {
  // Capture the token exactly once, on mount, then scrub the fragment.
  const tokenRef = useRef<string | null>(null);
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const hash = window.location.hash || "";
    const match = hash.match(/token=([^&]+)/);
    tokenRef.current = match ? decodeURIComponent(match[1]) : null;
    // Strip the token from the address bar without adding a history entry.
    window.history.replaceState(null, "", window.location.pathname);
    setReady(true);
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    if (!tokenRef.current) {
      setError("This invitation link is invalid or has expired.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      await acceptInvitation(tokenRef.current, password, confirm);
      // Full navigation so the AuthProvider re-bootstraps from the new session cookie.
      window.location.assign("/app");
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Something went wrong. Please try again.";
      setError(msg);
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-neutral-950 text-neutral-100 p-4">
      <meta name="referrer" content="no-referrer" />
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 rounded-2xl bg-neutral-900/80 p-6 shadow-xl"
      >
        <h1 className="text-xl font-semibold">Set your password</h1>
        <p className="text-sm text-neutral-400">
          Choose a password to activate your workspace.
        </p>

        <label className="block text-sm">
          <span className="mb-1 block text-neutral-300">New password</span>
          <input
            type={show ? "text" : "password"}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={15}
            className="w-full rounded-lg bg-neutral-800 px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-neutral-300">Confirm password</span>
          <input
            type={show ? "text" : "password"}
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={15}
            className="w-full rounded-lg bg-neutral-800 px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </label>

        <label className="flex items-center gap-2 text-xs text-neutral-400">
          <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} />
          Show password
        </label>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={submitting || !ready}
          className="w-full rounded-lg bg-indigo-600 px-3 py-2 font-medium hover:bg-indigo-500 disabled:opacity-50"
        >
          {submitting ? "Activating…" : "Activate account"}
        </button>
      </form>
    </div>
  );
}
