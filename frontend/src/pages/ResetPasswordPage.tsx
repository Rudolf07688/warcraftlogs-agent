import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, resetPassword } from "../api/restClient";
import { AuthShell } from "../components/AuthShell";
import { Button } from "../components/ui/button";
import { Field, FieldError, FieldLabel } from "../components/ui/field";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

/**
 * Password reset via a founder-shared link (feature 006, US5). Reads the single-use token
 * from the fragment, strips it immediately, sets a new password, then routes to /login
 * (completing a reset revokes all sessions server-side, so the user must sign in again).
 */
export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const tokenRef = useRef<string | null>(null);
  const ids = { password: useId(), confirm: useId() };
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
    <AuthShell>
      <meta name="referrer" content="no-referrer" />
      {done ? (
        <div className="space-y-4 text-center">
          <h1 className="text-xl font-semibold">Password updated</h1>
          <p className="text-sm text-muted-foreground">Sign in with your new password.</p>
          <Button className="w-full" onClick={() => navigate("/login", { replace: true })}>
            Go to sign in
          </Button>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <h1 className="text-xl font-semibold">Set a new password</h1>
          <Field>
            <FieldLabel htmlFor={ids.password}>New password</FieldLabel>
            <Input
              id={ids.password}
              type={show ? "text" : "password"}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={15}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor={ids.confirm}>Confirm password</FieldLabel>
            <Input
              id={ids.confirm}
              type={show ? "text" : "password"}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              minLength={15}
            />
          </Field>
          <Label className="text-xs font-normal text-muted-foreground">
            <input
              type="checkbox"
              className="accent-primary"
              checked={show}
              onChange={(e) => setShow(e.target.checked)}
            />
            Show password
          </Label>
          <FieldError>{error}</FieldError>
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "Updating…" : "Update password"}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
