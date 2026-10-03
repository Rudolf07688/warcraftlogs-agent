import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, resetPassword } from "../api/restClient";

/**
 * Password reset via a founder-shared link (feature 006, US5). Reads the single-use token
 * from the fragment, strips it immediately, sets a new password, then routes to /login
 * (completing a reset revokes all sessions server-side, so the user must sign in again).
 */
export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const tokenRef = useRef<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const match = (window.location.hash || "").match(/token=([^&]+)/);
    tokenRef.current = match ? decodeURIComponent(match[1]) : null;
    window.history.replaceState(null, "", window.location.pathname);
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    if (!tokenRef.current) {
      setError("This reset link is invalid or has expired.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      await resetPassword(tokenRef.current, password, confirm);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-neutral-950 text-neutral-100 p-4">
      <meta name="referrer" content="no-referrer" />
      {done ? (
        <div className="w-full max-w-sm space-y-4 rounded-2xl bg-neutral-900/80 p-6 text-center shadow-xl">
          <h1 className="text-xl font-semibold">Password updated</h1>
          <p className="text-sm text-neutral-400">Sign in with your new password.</p>
          <button
            onClick={() => navigate("/login", { replace: true })}
            className="w-full rounded-lg bg-indigo-600 px-3 py-2 font-medium hover:bg-indigo-500"
          >
            Go to sign in
          </button>
        </div>
      ) : (
        <form
          onSubmit={onSubmit}
          className="w-full max-w-sm space-y-4 rounded-2xl bg-neutral-900/80 p-6 shadow-xl"
        >
          <h1 className="text-xl font-semibold">Set a new password</h1>
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
            disabled={submitting}
            className="w-full rounded-lg bg-indigo-600 px-3 py-2 font-medium hover:bg-indigo-500 disabled:opacity-50"
          >
            {submitting ? "Updating…" : "Update password"}
          </button>
        </form>
      )}
    </div>
  );
}
