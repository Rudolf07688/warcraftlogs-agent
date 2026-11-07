import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RaidSummaryPanel } from "./RaidSummaryPanel";
import { clearRaidSummaryCache } from "./summaryCache";

// contract:raid-summary (sprint 2026-11-07b): the page renders the stored data of one raid.
// fetch is mocked, so the real restClient send and the real URL building are exercised.

const EXAMPLE = {
  report_code: "a1B2c3D4e5F6g7H8",
  has_data: true,
  duration_ms: 9876000,
  participants: [{ name: "Thrall", class_name: "Shaman", spec: "Enhancement", role: "dps" }],
  my_characters: [
    {
      name: "Thrall",
      class_name: "Shaman",
      spec: "Enhancement",
      parses: [{ encounter: "Ulgrax the Devourer", difficulty: "Heroic", percentile: 87.4 }],
    },
  ],
  fetched_at: "2026-11-07T19:00:00Z",
};

function reply(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "x",
    json: async () => body,
  } as Response;
}

beforeEach(() => clearRaidSummaryCache());

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RaidSummaryPanel", () => {
  it("shows duration, participants by role and my parses from the contract example", async () => {
    const fetchMock = vi.fn(async () => reply(200, EXAMPLE));
    vi.stubGlobal("fetch", fetchMock);
    render(<RaidSummaryPanel reportCode="a1B2c3D4e5F6g7H8" />);
    await screen.findByText("2h 44m");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/raids/a1B2c3D4e5F6g7H8/summary",
      expect.objectContaining({ method: "GET" }),
    );
    const dps = screen.getByRole("group", { name: "DPS" });
    expect(dps.textContent).toContain("Thrall");
    expect(dps.textContent).toContain("Enhancement Shaman");
    const mine = screen.getByRole("region", { name: "My characters" });
    expect(mine.textContent).toContain("Ulgrax the Devourer (Heroic)");
    expect(mine.textContent).toContain("87%");
  });

  it("says so when nothing is stored", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        reply(200, { ...EXAMPLE, has_data: false, duration_ms: null, participants: [], my_characters: [], fetched_at: null }),
      ),
    );
    render(<RaidSummaryPanel reportCode="abc" />);
    await screen.findByText(/Nothing stored for this raid yet/);
  });

  it("a part missing on its own does not hide the others", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(200, { ...EXAMPLE, my_characters: [] })));
    render(<RaidSummaryPanel reportCode="abc" />);
    await screen.findByText("2h 44m");
    expect(screen.getByRole("region", { name: "Participants" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "My characters" })).toBeNull();
  });

  it("404 shows raid not found without a retry; a server error offers a retry", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(404, { detail: "nope" }))
      .mockResolvedValueOnce(reply(500, {}))
      .mockResolvedValueOnce(reply(200, EXAMPLE));
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = render(<RaidSummaryPanel reportCode="abc" />);
    await screen.findByText(/Raid not found/);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    unmount();

    render(<RaidSummaryPanel reportCode="abc" />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await screen.findByText("2h 44m");
  });

  it("encodes the report code in the request path", async () => {
    const fetchMock = vi.fn(async () => reply(200, EXAMPLE));
    vi.stubGlobal("fetch", fetchMock);
    render(<RaidSummaryPanel reportCode="../x/y" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect((fetchMock.mock.calls[0] as unknown[])[0]).toBe("/api/raids/..%2Fx%2Fy/summary");
  });

  it("a late answer for the raid the user left is dropped", async () => {
    let resolveA: (r: Response) => void = () => {};
    const fetchMock = vi.fn((url: string) =>
      url.includes("/AAA/")
        ? new Promise<Response>((res) => (resolveA = res))
        : Promise.resolve(reply(200, { ...EXAMPLE, duration_ms: 60000 })),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<RaidSummaryPanel reportCode="AAA" />);
    rerender(<RaidSummaryPanel reportCode="BBB" />);
    await screen.findByText("1m 0s");
    resolveA(reply(200, { ...EXAMPLE, duration_ms: 9876000 }));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText("2h 44m")).toBeNull();
    expect(screen.getByText("1m 0s")).toBeTruthy();
  });

  it("renders hostile names as text", async () => {
    const evil = '<img src=x onerror="alert(1)">';
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        reply(200, {
          ...EXAMPLE,
          participants: [{ name: evil, class_name: "**Shaman**", spec: null, role: null }],
        }),
      ),
    );
    const { container } = render(<RaidSummaryPanel reportCode="abc" />);
    await screen.findByText(evil);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("group", { name: "Other" })).toBeTruthy();
  });
  // Live F2: contract:raid-summary (as built #129, #152) allows a null class_name, encounter
  // and difficulty; the page printed "Traecie Frost null".
  it("renders a null class, encounter and difficulty as nothing, never the word null", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        reply(200, {
          ...EXAMPLE,
          participants: [{ name: "Løkke", class_name: null, spec: null, role: null }],
          my_characters: [
            {
              name: "Traecie",
              class_name: null,
              spec: "Frost",
              parses: [
                { encounter: null, difficulty: null, percentile: 50 },
                { encounter: "Ulgrax the Devourer", difficulty: null, percentile: null },
              ],
            },
          ],
        }),
      ),
    );
    render(<RaidSummaryPanel reportCode="abc" />);
    await screen.findByText("2h 44m");
    const mine = screen.getByRole("region", { name: "My characters" });
    expect(mine.textContent).toContain("Traecie");
    expect(mine.textContent).toContain("Frost");
    expect(mine.textContent).toContain("Ulgrax the Devourer");
    expect(mine.textContent).not.toContain("null");
    expect(screen.getByRole("region", { name: "Participants" }).textContent).not.toContain("null");
  });

  // PERF-001: tabs unmount, so each switch refetched the summary and could trip the 60/min limit.
  it("coming back to a raid within the TTL makes no second request", async () => {
    const fetchMock = vi.fn(async () => reply(200, EXAMPLE));
    vi.stubGlobal("fetch", fetchMock);
    const first = render(<RaidSummaryPanel reportCode="abc" />);
    await screen.findByText("2h 44m");
    first.unmount();
    render(<RaidSummaryPanel reportCode="abc" />);
    await screen.findByText("2h 44m");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("two quick mounts of one raid share a single in-flight request", async () => {
    let resolve: (r: Response) => void = () => {};
    const fetchMock = vi.fn(() => new Promise<Response>((res) => (resolve = res)));
    vi.stubGlobal("fetch", fetchMock);
    const first = render(<RaidSummaryPanel reportCode="abc" />);
    first.unmount();
    render(<RaidSummaryPanel reportCode="abc" />);
    resolve(reply(200, EXAMPLE));
    await screen.findByText("2h 44m");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("asks again once the TTL has passed, and never caches a failure", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(500, {}))
      .mockResolvedValueOnce(reply(200, EXAMPLE))
      .mockResolvedValueOnce(reply(200, { ...EXAMPLE, duration_ms: 60000 }));
    vi.stubGlobal("fetch", fetchMock);
    const real = Date.now();
    const now = vi.spyOn(Date, "now");
    now.mockReturnValue(real);
    const a = render(<RaidSummaryPanel reportCode="abc" />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await screen.findByText("2h 44m");
    expect(fetchMock).toHaveBeenCalledTimes(2); // the failed answer was not kept
    a.unmount();
    now.mockReturnValue(real + 61_000);
    render(<RaidSummaryPanel reportCode="abc" />);
    await screen.findByText("1m 0s");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    now.mockRestore();
  });

  it("a 429 says to try again in a minute, with a retry", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply(429, { detail: { code: "rate_limited" } })));
    render(<RaidSummaryPanel reportCode="abc" />);
    await screen.findByText(/Too many requests, try again in a minute/);
    expect(screen.queryByText(/Could not load/)).toBeNull();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});
