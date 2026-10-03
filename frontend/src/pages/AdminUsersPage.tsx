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
    <div className="min-h-screen bg-neutral-950 text-neutral-100 p-6">
      <div className="mx-auto max-w-4xl space-y-8">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Users &amp; invitations</h1>
          <Link to="/app" className="text-indigo-400 hover:text-indigo-300">
            ← Back to app
          </Link>
        </header>

        {error && <p className="rounded bg-red-900/40 px-3 py-2 text-sm text-red-300">{error}</p>}

        {/* Create invitation */}
        <section className="space-y-3 rounded-2xl bg-neutral-900/70 p-4">
          <h2 className="font-medium">Invite someone</h2>
          <form onSubmit={onCreate} className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="mb-1 block text-neutral-400">Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="rounded-lg bg-neutral-800 px-3 py-2 outline-none"
              />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-neutral-400">Role</span>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as Role)}
                className="rounded-lg bg-neutral-800 px-3 py-2 outline-none"
              >
                <option value="tenant_admin">tenant_admin</option>
                <option value="member">member</option>
              </select>
            </label>
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-indigo-600 px-4 py-2 font-medium hover:bg-indigo-500 disabled:opacity-50"
            >
              Create invite
            </button>
          </form>
          {freshLink && (
            <div className="rounded-lg bg-neutral-800 p-3 text-sm">
              <p className="mb-1 text-neutral-400">Copy &amp; share this link once:</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all text-indigo-300">{freshLink}</code>
                <button
                  onClick={() => navigator.clipboard?.writeText(freshLink)}
                  className="rounded bg-neutral-700 px-2 py-1 hover:bg-neutral-600"
                >
                  Copy
                </button>
              </div>
            </div>
          )}
        </section>

        {/* Pending invitations */}
        <section className="space-y-2 rounded-2xl bg-neutral-900/70 p-4">
          <h2 className="font-medium">Pending invitations</h2>
          {invites.length === 0 ? (
            <p className="text-sm text-neutral-500">None.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="text-neutral-400">
                <tr>
                  <th className="py-1">Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Expires</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {invites.map((i) => (
                  <tr key={i.id} className="border-t border-neutral-800">
                    <td className="py-2">{i.email}</td>
                    <td>{i.role}</td>
                    <td>{i.status}</td>
                    <td>{new Date(i.expires_at).toLocaleString()}</td>
                    <td className="space-x-2 text-right">
                      <button
                        disabled={busy}
                        onClick={() =>
                          run(async () => setFreshLink((await resendInvitation(i.id)).invite_link ?? null))
                        }
                        className="rounded bg-neutral-700 px-2 py-1 hover:bg-neutral-600"
                      >
                        Resend
                      </button>
                      <button
                        disabled={busy}
                        onClick={() => run(() => revokeInvitation(i.id))}
                        className="rounded bg-red-800 px-2 py-1 hover:bg-red-700"
                      >
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* Users */}
        <section className="space-y-2 rounded-2xl bg-neutral-900/70 p-4">
          <h2 className="font-medium">Users</h2>
          <table className="w-full text-left text-sm">
            <thead className="text-neutral-400">
              <tr>
                <th className="py-1">Email</th>
                <th>Status</th>
                <th>Last login</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-neutral-800">
                  <td className="py-2">{u.email}</td>
                  <td>{u.status}</td>
                  <td>{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "—"}</td>
                  <td className="space-x-2 text-right">
                    {u.status === "disabled" ? (
                      <button
                        disabled={busy}
                        onClick={() => run(async () => void (await setUserStatus(u.id, "active")))}
                        className="rounded bg-neutral-700 px-2 py-1 hover:bg-neutral-600"
                      >
                        Enable
                      </button>
                    ) : (
                      <button
                        disabled={busy}
                        onClick={() => {
                          if (confirm(`Disable ${u.email}?`))
                            void run(async () => void (await setUserStatus(u.id, "disabled")));
                        }}
                        className="rounded bg-red-800 px-2 py-1 hover:bg-red-700"
                      >
                        Disable
                      </button>
                    )}
                    <button
                      disabled={busy}
                      onClick={() => run(async () => setFreshLink((await triggerReset(u.id)).reset_link))}
                      className="rounded bg-neutral-700 px-2 py-1 hover:bg-neutral-600"
                    >
                      Reset link
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
