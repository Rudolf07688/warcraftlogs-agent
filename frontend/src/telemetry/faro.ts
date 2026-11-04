import type { withFaroRouterInstrumentation } from "@grafana/faro-react";
import { registerFaro, setTelemetryUser } from "./context";

// Feature 057 (sc-414): Grafana Faro in the browser, off unless VITE_FARO_URL is set.
// Config comes from VITE_FARO_* (compose passes them to the dev server). The API key in the
// bundle is public by design: the receiver's CORS list and rate limit are the protection.

export interface FaroEnv {
  url: string;
  apiKey?: string;
  version: string;
  environment: string;
}

type Env = Record<string, string | undefined>;

export function readFaroConfig(env: Env): FaroEnv | null {
  const url = env.VITE_FARO_URL?.trim();
  if (!url) return null;
  return {
    url,
    apiKey: env.VITE_FARO_API_KEY?.trim() || undefined,
    version: env.VITE_FARO_APP_VERSION?.trim() || "unknown",
    environment: env.VITE_FARO_ENVIRONMENT?.trim() || "dev",
  };
}

/** A one-way, salted SHA-256 prefix of the account id: pseudonymous, never the email. */
export async function hashUserId(userId: string): Promise<string | null> {
  try {
    const bytes = new TextEncoder().encode(`wcl-agent:${userId}`);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest).slice(0, 8), (b) => b.toString(16).padStart(2, "0")).join("");
  } catch {
    return null; // no WebCrypto (an insecure origin): report no user rather than a weaker id
  }
}

/** Report the signed-in account to Faro as a hash; null on sign-out. */
export async function identifyUser(userId: string | null): Promise<void> {
  setTelemetryUser(userId ? await hashUserId(userId) : null);
}

type DataRouter = Parameters<typeof withFaroRouterInstrumentation>[0];

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Starts Faro with web tracing and the data-router instrumentation. Resolves false (and loads
 * none of the Faro packages) when no endpoint is configured.
 */
export async function initTelemetry(router: DataRouter, env: Env = import.meta.env): Promise<boolean> {
  const config = readFaroConfig(env);
  if (!config) return false;
  const [react, tracing, routerDom] = await Promise.all([
    import("@grafana/faro-react"),
    import("@grafana/faro-web-tracing"),
    import("react-router-dom"),
  ]);
  const faro = react.initializeFaro({
    url: config.url,
    apiKey: config.apiKey,
    app: { name: "web", namespace: "wcl-agent", version: config.version, environment: config.environment },
    // Console output can carry anything the app logs; errors, vitals and traces are enough.
    instrumentations: [
      ...react.getWebInstrumentations({ captureConsole: false }),
      new tracing.TracingInstrumentation({
        // An unsampled session sends no traceparent: the backend decides its own sampling.
        omitTraceContextForUnsampledSessions: true,
        // Same-origin calls (the Vite proxy) get traceparent; nothing else does.
        instrumentationOptions: {
          propagateTraceHeaderCorsUrls: [new RegExp(`^${escapeRegExp(location.origin)}/`)],
        },
      }),
      new react.ReactIntegration({
        router: react.createReactRouterV7DataOptions({ matchRoutes: routerDom.matchRoutes }),
      }),
    ],
  });
  registerFaro(faro);
  react.withFaroRouterInstrumentation(router);
  return true;
}
