import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  createInvitation,
  listInvitations,
  listUsers,
  resendInvitation,
  revokeInvitation,
  setUserStatus,
  triggerReset,
} from "../api/restClient";
import type { AdminUser, Invitation, Role } from "../types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { StatusAlert } from "../components/StatusAlert";
import { INVITE_TONE, StatusBadge, toneFor, USER_TONE } from "../components/StatusBadge";
import { Button } from "../components/ui/button";
import { Field, FieldLabel } from "../components/ui/field";
import { Input } from "../components/ui/input";
import { NativeSelect, NativeSelectOption } from "../components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";

/**
 * Platform-admin surface (feature 006, US4): manage users + invitations. Server enforces
 * authz on every call; this page only hides what the user can't do. Secrets (hashes/tokens)
 * are never rendered — the one-time invite/reset link is shown only right after it's minted.
 */
export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [invites, setInvites] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("tenant_admin");
  const [freshLink, setFreshLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Feature 010 / FR-006: the user awaiting the in-app disable confirmation.
  const [pendingDisable, setPendingDisable] = useState<AdminUser | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [u, i] = await Promise.all([listUsers(), listInvitations()]);
      setUsers(u.users);
      setInvites(i.invitations);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    await run(async () => {
      const inv = await createInvitation(email, role);
      setFreshLink(inv.invite_link ?? null);
      setEmail("");
    });
  }

  return (
    <div className="min-h-screen bg-background text-foreground p-6">
      <div className="mx-auto max-w-4xl space-y-8">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Users &amp; invitations</h1>
          <Button asChild variant="secondary">
            <Link to="/app">← Back to app</Link>
          </Button>
        </header>

        {error && (
          <StatusAlert tone="error" onDismiss={() => setError(null)}>
            {error}
          </StatusAlert>
        )}

        {/* Create invitation */}
        <section className="space-y-3 rounded-2xl border border-border bg-card p-4">
          <h2 className="font-medium">Invite someone</h2>
          <form onSubmit={onCreate} className="flex flex-wrap items-end gap-3">
            <Field className="w-auto">
              <FieldLabel htmlFor="invite-email">Email</FieldLabel>
              <Input
                id="invite-email"
                type="email"
                className="w-64"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </Field>
            <Field className="w-auto">
              <FieldLabel htmlFor="invite-role">Role</FieldLabel>
              <NativeSelect
                id="invite-role"
                value={role}
                onChange={(e) => setRole(e.target.value as Role)}
              >
                <NativeSelectOption value="tenant_admin">tenant_admin</NativeSelectOption>
                <NativeSelectOption value="member">member</NativeSelectOption>
              </NativeSelect>
            </Field>
            <Button type="submit" disabled={busy}>
              Create invite
            </Button>
          </form>
          {freshLink && (
            <div className="rounded-lg border border-border bg-secondary p-3 text-sm">
              <p className="mb-1 text-muted-foreground">Copy &amp; share this link once:</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all text-primary">{freshLink}</code>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => navigator.clipboard?.writeText(freshLink)}
                >
                  Copy
                </Button>
              </div>
            </div>
          )}
        </section>

        {/* Pending invitations */}
        <section className="space-y-2 rounded-2xl border border-border bg-card p-4">
          <h2 className="font-medium">Pending invitations</h2>
          {invites.length === 0 ? (
            <p className="text-sm text-muted-foreground">None.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {invites.map((i) => (
                  <TableRow key={i.id}>
                    <TableCell>{i.email}</TableCell>
                    <TableCell>{i.role}</TableCell>
                    <TableCell>
                      <StatusBadge tone={toneFor(INVITE_TONE, i.status)}>{i.status}</StatusBadge>
                    </TableCell>
                    <TableCell>{new Date(i.expires_at).toLocaleString()}</TableCell>
                    <TableCell className="space-x-2 text-right">
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={busy}
                        onClick={() =>
                          run(async () => setFreshLink((await resendInvitation(i.id)).invite_link ?? null))
                        }
                      >
                        Resend
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        disabled={busy}
                        onClick={() => run(() => revokeInvitation(i.id))}
                      >
                        Revoke
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </section>

        {/* Users */}
        <section className="space-y-2 rounded-2xl border border-border bg-card p-4">
          <h2 className="font-medium">Users</h2>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last login</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id}>
                  <TableCell>{u.email}</TableCell>
                  <TableCell>
                    <StatusBadge tone={toneFor(USER_TONE, u.status)}>{u.status}</StatusBadge>
                  </TableCell>
                  <TableCell>{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "—"}</TableCell>
                  <TableCell className="space-x-2 text-right">
                    {u.status === "disabled" ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={busy}
                        onClick={() => run(async () => void (await setUserStatus(u.id, "active")))}
                      >
                        Enable
                      </Button>
                    ) : (
                      <Button
                        variant="destructive"
                        size="sm"
                        disabled={busy}
                        onClick={() => setPendingDisable(u)}
                      >
                        Disable
                      </Button>
                    )}
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={busy}
                      onClick={() => run(async () => setFreshLink((await triggerReset(u.id)).reset_link))}
                    >
                      Reset link
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      </div>

      <ConfirmDialog
        open={pendingDisable !== null}
        title="Disable user?"
        description={`${pendingDisable?.email ?? ""} will no longer be able to sign in.`}
        confirmLabel="Disable"
        busy={busy}
        onConfirm={async () => {
          const target = pendingDisable;
          if (!target) return;
          await run(async () => void (await setUserStatus(target.id, "disabled")));
          setPendingDisable(null);
        }}
        onCancel={() => setPendingDisable(null)}
      />
    </div>
  );
}
