import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, type RouteObject } from "react-router-dom";
import App from "./App";
import { RequireAuth } from "./auth/RequireAuth";
import { RouteErrorFallback } from "./telemetry/ErrorBoundary";

// PERF-011: the chat (App) loads eagerly; every other page is its own chunk, fetched the
// first time it's visited. KaTeX styles load with the math plugin (StreamMarkdown).
const AcceptInvitePage = lazy(() => import("./pages/AcceptInvitePage"));
const AdminUsersPage = lazy(() => import("./pages/AdminUsersPage"));
const ForbiddenPage = lazy(() => import("./pages/ForbiddenPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const ResetPasswordPage = lazy(() => import("./pages/ResetPasswordPage"));

function Page({ children }: { children: ReactNode }) {
  return <Suspense fallback={null}>{children}</Suspense>;
}

// feature 006: public auth routes vs. the guarded app shell.
// A pathless root route owns the errorElement: a render error in any route (App outside its
// panels, profile, admin, login) shows the plain fallback instead of React Router's default
// page with the raw message and stack (feature 060).
export const appRoutes: RouteObject[] = [
  {
    errorElement: <RouteErrorFallback />,
    children: [
      { path: "/login", element: <Page><LoginPage /></Page> },
      { path: "/accept-invite", element: <Page><AcceptInvitePage /></Page> },
      { path: "/reset-password", element: <Page><ResetPasswordPage /></Page> },
      { path: "/forbidden", element: <Page><ForbiddenPage /></Page> },
      {
        path: "/app/*",
        element: (
          <RequireAuth>
            <App />
          </RequireAuth>
        ),
      },
      {
        path: "/profile",
        element: (
          <RequireAuth>
            <Page>
              <ProfilePage />
            </Page>
          </RequireAuth>
        ),
      },
      {
        path: "/admin/users",
        element: (
          <RequireAuth adminOnly>
            <Page>
              <AdminUsersPage />
            </Page>
          </RequireAuth>
        ),
      },
      { path: "*", element: <Navigate to="/app" replace /> },
    ],
  },
];
