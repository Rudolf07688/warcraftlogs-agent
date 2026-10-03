import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth/AuthProvider";
import { RequireAuth } from "./auth/RequireAuth";
import AcceptInvitePage from "./pages/AcceptInvitePage";
import AdminUsersPage from "./pages/AdminUsersPage";
import ForbiddenPage from "./pages/ForbiddenPage";
import LoginPage from "./pages/LoginPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import "katex/dist/katex.min.css"; // US3: math typesetting styles
import "./styles.css";
import "./index.css";

// feature 006: public auth routes vs. the guarded app shell. AuthProvider wraps the whole
// tree so every route can read the identity / rehydrate the session on load.
const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/accept-invite", element: <AcceptInvitePage /> },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  { path: "/forbidden", element: <ForbiddenPage /> },
  {
    path: "/app/*",
    element: (
      <RequireAuth>
        <App />
      </RequireAuth>
    ),
  },
  {
    path: "/admin/users",
    element: (
      <RequireAuth adminOnly>
        <AdminUsersPage />
      </RequireAuth>
    ),
  },
  { path: "*", element: <Navigate to="/app" replace /> },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  </StrictMode>,
);
