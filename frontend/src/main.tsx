import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import { BackendBootGate } from "./components/BackendBootGate";
import { TelemetryBoundary } from "./telemetry/ErrorBoundary";
import { appRoutes } from "./routes";
import { initTelemetry } from "./telemetry/faro";
import "./styles.css";
import "./index.css";

// feature 006: AuthProvider wraps the whole tree so every route can read the identity /
// rehydrate the session on load.
const router = createBrowserRouter(appRoutes);

// Feature 057: Faro (browser traces, Web Vitals, route events), only when VITE_FARO_URL is set.
void initTelemetry(router);

// BackendBootGate sits outermost: nothing (not even the auth rehydrate) talks to the API
// until the backend reports every startup step done. Shows a boot overlay meanwhile.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BackendBootGate>
      <AuthProvider>
        {/* Feature 060: the last line of defence; each chat panel has its own boundary. */}
        <TelemetryBoundary name="shell">
          <RouterProvider router={router} />
        </TelemetryBoundary>
      </AuthProvider>
    </BackendBootGate>
  </StrictMode>,
);
