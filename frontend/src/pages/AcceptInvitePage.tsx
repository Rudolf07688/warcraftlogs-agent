import { useEffect, useId, useRef, useState } from "react";
import { acceptInvitation, ApiError } from "../api/restClient";
import { AuthShell } from "../components/AuthShell";
import { Button } from "../components/ui/button";
import { Field, FieldError, FieldLabel } from "../components/ui/field";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

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
  const ids = { password: useId(), confirm: useId() };
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
    <AuthShell>
      <meta name="referrer" content="no-referrer" />
      <form onSubmit={onSubmit} className="space-y-4">
        <h1 className="text-xl font-semibold">Set your password</h1>
        <p className="text-sm text-muted-foreground">
          Choose a password to activate your workspace.
        </p>

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

        <Button type="submit" className="w-full" disabled={submitting || !ready}>
          {submitting ? "Activating…" : "Activate account"}
        </Button>
      </form>
    </AuthShell>
  );
}
