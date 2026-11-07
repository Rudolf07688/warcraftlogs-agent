import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RaidSummaryPanel } from "./RaidSummaryPanel";

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
});
