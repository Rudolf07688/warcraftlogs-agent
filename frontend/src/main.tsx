import { lazy, StrictMode, Suspense, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth/AuthProvider";
import { RequireAuth } from "./auth/RequireAuth";
import { BackendBootGate } from "./components/BackendBootGate";
import "./styles.css";
import "./index.css";

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

// feature 006: public auth routes vs. the guarded app shell. AuthProvider wraps the whole
// tree so every route can read the identity / rehydrate the session on load.
const router = createBrowserRouter([
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
]);

// BackendBootGate sits outermost: nothing (not even the auth rehydrate) talks to the API
// until the backend reports every startup step done. Shows a boot overlay meanwhile.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BackendBootGate>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </BackendBootGate>
  </StrictMode>,
);
