import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./useAuth";

/**
 * Route guard (feature 006). UX-only — the server is the real authority. Redirects
 * unauthenticated users to /login, and non-admins away from admin-only routes.
 */
export function RequireAuth({
  children,
  adminOnly = false,
}: {
  children: ReactNode;
  adminOnly?: boolean;
}) {
  const { identity, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-neutral-950 text-neutral-400">
        Loading…
      </div>
    );
  }
  if (!identity) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (adminOnly && !identity.is_platform_admin) {
    return <Navigate to="/forbidden" replace />;
  }
  return <>{children}</>;
}
