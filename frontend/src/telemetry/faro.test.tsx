import { afterEach, describe, expect, it, vi } from "vitest";
import { faroSessionId, resetFaroForTests } from "./context";
import { hashUserId, identifyUser, initTelemetry, readFaroConfig } from "./faro";

// Feature 057 (sc-414): Faro initialises only with an endpoint; the user is a hash.

const h = vi.hoisted(() => ({
  initializeFaro: vi.fn(),
  withFaroRouterInstrumentation: vi.fn(),
  setUser: vi.fn(),
}));

vi.mock("@grafana/faro-react", () => ({
  initializeFaro: h.initializeFaro,
  getWebInstrumentations: vi.fn(() => ["web"]),
  ReactIntegration: class {},
  createReactRouterV7DataOptions: vi.fn(() => ({})),
  withFaroRouterInstrumentation: h.withFaroRouterInstrumentation,
}));
vi.mock("@grafana/faro-web-tracing", () => ({ TracingInstrumentation: class {} }));

afterEach(() => {
  resetFaroForTests();
  vi.clearAllMocks();
});

const router = { state: {}, routes: [], subscribe: () => () => {} } as never;

describe("readFaroConfig", () => {
  it.each([{}, { VITE_FARO_URL: "" }, { VITE_FARO_URL: "   " }])("is off for %j", (env) => {
    expect(readFaroConfig(env)).toBeNull();
  });

  it("reads the endpoint, key, version and environment", () => {
    expect(
      readFaroConfig({
        VITE_FARO_URL: "http://localhost:12347/collect",
        VITE_FARO_API_KEY: "k",
        VITE_FARO_APP_VERSION: "abc123",
      }),
    ).toEqual({ url: "http://localhost:12347/collect", apiKey: "k", version: "abc123", environment: "dev" });
  });
});

describe("initTelemetry", () => {
  it("never initialises Faro without an endpoint", async () => {
    expect(await initTelemetry(router, {})).toBe(false);
    expect(h.initializeFaro).not.toHaveBeenCalled();
    expect(h.withFaroRouterInstrumentation).not.toHaveBeenCalled();
    expect(faroSessionId()).toBeUndefined();
  });

  it("starts Faro with the endpoint and wraps the router when configured", async () => {
    h.initializeFaro.mockReturnValue({ api: { getSession: () => ({ id: "s1" }), setUser: h.setUser, resetUser: vi.fn() } });
    const env = { VITE_FARO_URL: "http://localhost:12347/collect", VITE_FARO_API_KEY: "k" };

    expect(await initTelemetry(router, env)).toBe(true);

    const config = h.initializeFaro.mock.calls[0][0];
    expect(config).toMatchObject({ url: env.VITE_FARO_URL, apiKey: "k", app: { name: "web" } });
    expect(h.withFaroRouterInstrumentation).toHaveBeenCalledWith(router);
    expect(faroSessionId()).toBe("s1");
  });
});

describe("the user hash", () => {
  it("is a short one-way hex string that holds neither the id nor an email", async () => {
    const hash = await hashUserId("3f2c7a9e-0000-4000-8000-123456789abc");
    expect(hash).toMatch(/^[0-9a-f]{16}$/);
    expect(hash).not.toContain("3f2c");
    expect(await hashUserId("3f2c7a9e-0000-4000-8000-123456789abc")).toBe(hash);
    expect(await hashUserId("another-id")).not.toBe(hash);
  });

  it("goes to Faro on sign-in and is cleared on sign-out", async () => {
    const resetUser = vi.fn();
    h.initializeFaro.mockReturnValue({ api: { getSession: () => undefined, setUser: h.setUser, resetUser } });
    await initTelemetry(router, { VITE_FARO_URL: "http://x/collect" });

    await identifyUser("user-1");
    expect(h.setUser).toHaveBeenLastCalledWith({ id: await hashUserId("user-1") });
    await identifyUser(null);
    expect(resetUser).toHaveBeenCalled();
  });
});
