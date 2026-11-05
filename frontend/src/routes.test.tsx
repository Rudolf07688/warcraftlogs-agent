import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { registerFaro, resetFaroForTests } from "./telemetry/context";
import { appRoutes } from "./routes";

// Feature 060 (sc-416): the app's own route tree turns a route render error into the plain
// fallback (never React Router's default page with the message and stack) and reports it.

const SECRET_TEXT = "WCL said: token abc123 for report XYZ";

vi.mock("./App", () => ({
  default: () => {
    throw new Error(SECRET_TEXT);
  },
}));
vi.mock("./auth/RequireAuth", () => ({ RequireAuth: ({ children }: { children: unknown }) => children }));

afterEach(() => {
  cleanup();
  resetFaroForTests();
  vi.restoreAllMocks();
});

describe("appRoutes", () => {
  it("a route element that throws shows the plain fallback and reports once", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const pushError = vi.fn();
    registerFaro({
      api: { pushError, setView: vi.fn(), setUser: vi.fn(), resetUser: vi.fn(), pushEvent: vi.fn() },
    } as never);
    const router = createMemoryRouter(appRoutes, { initialEntries: ["/app"] });
    const { container } = render(<RouterProvider router={router} />);
    expect(screen.getByRole("alert").textContent).toContain("Something went wrong");
    expect(container.textContent).not.toContain("abc123");
    expect(container.textContent).not.toContain("Unexpected Application Error");
    expect(container.querySelector("pre")).toBeNull();
    expect(pushError).toHaveBeenCalledTimes(1);
    expect(pushError.mock.calls[0][1].context.boundary).toBe("shell");
  });
});
