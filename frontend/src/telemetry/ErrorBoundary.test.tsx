import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { registerFaro, resetFaroForTests, setRoute } from "./context";
import { TelemetryBoundary } from "./ErrorBoundary";

// Feature 060 (sc-416): a panel that throws shows a plain fallback (never the error's text),
// reports once to Faro with its route and boundary, and leaves the other panels mounted.

const SECRET_TEXT = "WCL said: token abc123 for report XYZ";

function Boom({ explode }: { explode: boolean }) {
  if (explode) throw new Error(SECRET_TEXT);
  return <p>panel ok</p>;
}

function fakeFaro() {
  const api = {
    getOTEL: vi.fn(),
    getSession: vi.fn(),
    setUser: vi.fn(),
    resetUser: vi.fn(),
    setView: vi.fn(),
    pushEvent: vi.fn(),
    pushError: vi.fn(),
  };
  registerFaro({ api } as never);
  return api;
}

afterEach(() => {
  cleanup();
  resetFaroForTests();
  vi.restoreAllMocks();
});

function quietConsole() {
  vi.spyOn(console, "error").mockImplementation(() => {}); // React logs caught errors
}

describe("TelemetryBoundary", () => {
  it("renders the fallback without the error's message or stack", () => {
    quietConsole();
    fakeFaro();
    const { container } = render(
      <TelemetryBoundary name="messages">
        <Boom explode />
      </TelemetryBoundary>,
    );
    expect(screen.getByRole("alert").textContent).toContain("Something went wrong");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(container.textContent).not.toContain("abc123");
    expect(container.textContent).not.toContain("Boom");
  });

  it("reports once to Faro with the route template and the boundary name", () => {
    quietConsole();
    const api = fakeFaro();
    setRoute("/app/*");
    render(
      <TelemetryBoundary name="messages">
        <Boom explode />
      </TelemetryBoundary>,
    );
    expect(api.pushError).toHaveBeenCalledTimes(1);
    const [error, options] = api.pushError.mock.calls[0];
    expect(error.name).toBe("React ErrorBoundary Error");
    expect(error.stack).toContain("Boom"); // the component stack, not the JS stack
    expect(options).toEqual({ context: { boundary: "messages", route: "/app/*" } });
  });

  it("keeps the sibling panels mounted", () => {
    quietConsole();
    fakeFaro();
    render(
      <TelemetryBoundary name="shell">
        <TelemetryBoundary name="sidebar">
          <p>sidebar ok</p>
        </TelemetryBoundary>
        <TelemetryBoundary name="messages">
          <Boom explode />
        </TelemetryBoundary>
        <TelemetryBoundary name="composer">
          <p>composer ok</p>
        </TelemetryBoundary>
      </TelemetryBoundary>,
    );
    expect(screen.getByText("sidebar ok")).toBeTruthy();
    expect(screen.getByText("composer ok")).toBeTruthy();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("renders the panel again on Retry", () => {
    quietConsole();
    fakeFaro();
    function Harness() {
      const [explode, setExplode] = useState(true);
      return (
        <>
          <button onClick={() => setExplode(false)}>fix</button>
          <TelemetryBoundary name="messages">
            <Boom explode={explode} />
          </TelemetryBoundary>
        </>
      );
    }
    render(<Harness />);
    fireEvent.click(screen.getByText("fix"));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(screen.getByText("panel ok")).toBeTruthy();
  });

  it("shows the fallback while Faro is off", () => {
    quietConsole();
    render(
      <TelemetryBoundary name="messages">
        <Boom explode />
      </TelemetryBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
  });
});
