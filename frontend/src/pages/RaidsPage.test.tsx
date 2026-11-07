import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import RaidsPage from "./RaidsPage";
import type { Raid } from "../types";

vi.mock("../api/raidSummary", () => ({
  getRaidSummary: vi.fn(async () => ({
    report_code: "x",
    has_data: false,
    duration_ms: null,
    participants: [],
    my_characters: [],
    fetched_at: null,
  })),
}));
import { getRaidSummary } from "../api/raidSummary";
import { clearRaidSummaryCache } from "../components/raids/summaryCache";

function raid(code: string, label: string, started: string): Raid {
  return {
    report_code: code,
    label,
    zone: "Nerub-ar Palace",
    guild: "Guild",
    report_started_at: started,
    last_asked_at: started,
    first_seen_at: started,
    encounters: [{ encounter_id: 1, name: "Ulgrax", kill: true }],
  };
}

const RAIDS = [
  raid("OLD", "Old raid", "2026-11-01T19:00:00Z"),
  raid("NEW", "New raid", "2026-11-05T19:00:00Z"),
  raid("MID", "Mid raid", "2026-11-03T19:00:00Z"),
];

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function renderPage(over: Partial<React.ComponentProps<typeof RaidsPage>> = {}, path = "/app/raids") {
  const props = {
    raids: RAIDS,
    status: "ready" as const,
    reportCode: undefined,
    streaming: false,
    connected: true,
    error: null,
    onAnalyze: vi.fn(),
    ...over,
  };
  render(
    <MemoryRouter initialEntries={[path]}>
      <RaidsPage {...props} />
      <Where />
    </MemoryRouter>,
  );
  return props;
}

beforeEach(() => clearRaidSummaryCache());

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RaidsPage", () => {
  it("one tab per raid, newest first and selected; the address picks another", () => {
    renderPage();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["New raid", "Mid raid", "Old raid"]);
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(getRaidSummary).toHaveBeenCalledTimes(1);
    expect(vi.mocked(getRaidSummary).mock.calls[0][0]).toBe("NEW");

    fireEvent.mouseDown(tabs[2]); // Radix activates on mousedown
    expect(screen.getByTestId("where").textContent).toBe("/app/raids/OLD");
  });

  it("a reportCode from the address selects that tab", () => {
    renderPage({ reportCode: "MID" });
    expect(screen.getByRole("tab", { name: "Mid raid" }).getAttribute("aria-selected")).toBe("true");
    expect(vi.mocked(getRaidSummary).mock.calls.map((c) => c[0])).toEqual(["MID"]);
  });

  it.each(["NOPE", "../", "a/b"])("an unknown code %s shows not found and makes no request", (code) => {
    renderPage({ reportCode: code });
    expect(screen.getByText(/Raid not found/)).toBeTruthy();
    expect(getRaidSummary).not.toHaveBeenCalled();
  });

  it("Analyze this raid hands the selected raid's code to the shell", () => {
    const props = renderPage({ reportCode: "MID" });
    fireEvent.click(screen.getByRole("button", { name: "Analyze this raid" }));
    expect(props.onAnalyze).toHaveBeenCalledWith("MID");
  });

  it("Analyze is disabled while an answer streams", () => {
    const props = renderPage({ streaming: true });
    const btn = screen.getByRole("button", { name: "Analyze this raid" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);
    expect(props.onAnalyze).not.toHaveBeenCalled();
  });

  it("Analyze is disabled while the chat socket is disconnected, like the composer", () => {
    const props = renderPage({ connected: false });
    const btn = screen.getByRole("button", { name: "Analyze this raid" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);
    expect(props.onAnalyze).not.toHaveBeenCalled();
  });

  it("shows loading, empty and error states and the shell's error", () => {
    cleanup();
    renderPage({ status: "loading", raids: [] });
    expect(screen.getByText(/Loading raids/)).toBeTruthy();
    cleanup();
    renderPage({ raids: [] });
    expect(screen.getByText("No raids tracked yet")).toBeTruthy();
    cleanup();
    renderPage({ error: "Could not start the investigation. Is the backend up?" });
    expect(screen.getByRole("alert").textContent).toContain("Could not start the investigation");
  });

  it("renders hostile and very long raid text as text, truncated by CSS", () => {
    const evil = '<img src=x onerror="alert(1)">' + "x".repeat(300);
    const r = { ...raid("EVIL", evil, "2026-11-06T19:00:00Z"), guild: "**bold**", zone: "<b>zone</b>" };
    renderPage({ raids: [r] });
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("b")).toBeNull();
    const tab = screen.getByRole("tab");
    expect(tab.textContent).toBe(evil);
    expect(tab.className).toContain("max-w-56");
    expect(tab.querySelector(".truncate")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2 }).className).toContain("truncate");
    expect(screen.getByTestId("raid-tabs-scroll").className).toContain("overflow-x-auto");
  });
});
