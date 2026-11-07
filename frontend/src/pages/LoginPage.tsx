import { useId, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError, getProfileSettings } from "../api/restClient";
import { afterLoginPath } from "../auth/redirect";
import { useAuth } from "../auth/useAuth";
import { AuthShell } from "../components/AuthShell";
import { Button } from "../components/ui/button";
import { Field, FieldError, FieldLabel } from "../components/ui/field";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: unknown } | null)?.from;
  const ids = { email: useId(), password: useId() };

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      // Feature 074: with no own character and the welcome prompt never skipped, the
      // player lands on the profile page (when headed for the chat home).
      const pending = await getProfileSettings().then(
        (s) => s.onboarding_pending,
        () => false, // can't tell: go where the player was going
      );
      navigate(afterLoginPath(from, pending), { replace: true });
    } catch (err) {
      // Generic message regardless of cause (no account enumeration).
      setError(
        err instanceof ApiError && err.status === 429
          ? "Too many attempts. Please wait a moment and try again."
          : "Invalid email or password.",
      );
      setSubmitting(false);
    }
  }

  return (
    <AuthShell>
      <form onSubmit={onSubmit} className="space-y-4">
        <h1 className="text-xl font-semibold">Sign in</h1>

        <Field>
          <FieldLabel htmlFor={ids.email}>Email</FieldLabel>
          <Input
            id={ids.email}
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </Field>

        <Field>
          <FieldLabel htmlFor={ids.password}>Password</FieldLabel>
          <Input
            id={ids.password}
            type={show ? "text" : "password"}
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
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
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthShell>
  );
}
