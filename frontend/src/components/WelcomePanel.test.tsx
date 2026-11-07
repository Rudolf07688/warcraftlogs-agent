import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { getPortraits } from "../api/portraits";
import { getRecentRaids } from "../api/restClient";
import { resetPortraitsCache } from "../hooks/usePortraits";
import type { RecentRaidsResponse } from "../types";
import { WelcomePanel } from "./WelcomePanel";

// Feature 075 (sc-364): a recent raid shows its characters' portraits, matched by identity.

vi.mock("../api/restClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/restClient")>()),
  getRecentRaids: vi.fn(),
}));
vi.mock("../api/portraits", () => ({ getPortraits: vi.fn() }));

const AVATAR = "https://render.worldofwarcraft.com/eu/character/tarren-mill/1/2-avatar.jpg";

const DATA: RecentRaidsResponse = {
  has_characters: true,
  raids: [
    {
      report_code: "a1B2c3D4e5F6g7H8",
      title: "Raid night",
      zone_name: "Nerub-ar Palace",
      started_at: new Date().toISOString(),
      difficulty: 4,
      bosses_pulled: 8,
      bosses_killed: 8,
      is_final: true,
      characters: [
        { name: "Kazrok", server: "tarren-mill", region: "EU" },
        { name: "Velyra", server: "Tarren Mill", region: "eu" },
      ],
    },
  ],
  mplus_runs: [],
  refresh: { status: "succeeded", last_success_at: null, last_error: null },
};

beforeEach(() => {
  resetPortraitsCache();
  vi.mocked(getRecentRaids).mockResolvedValue(DATA);
  vi.mocked(getPortraits).mockResolvedValue({
    portraits: [
      { character_id: "c1", name: "Kazrok", server: "Tarren Mill", region: "eu", class_name: "Druid", portrait_url: AVATAR },
      { character_id: "c2", name: "Velyra", server: "Tarren Mill", region: "eu", class_name: "Mage", portrait_url: null },
    ],
  });
});
afterEach(cleanup);

describe("WelcomePanel portraits", () => {
  it("shows the portrait beside a character who has one and initials beside one who doesn't", async () => {
    const { container, findByText } = render(
      <MemoryRouter>
        <WelcomePanel onInvestigate={() => {}} onInvestigateMplus={() => {}} disabled={false} />
      </MemoryRouter>,
    );
    await findByText("Kazrok, Velyra");
    await waitFor(() => expect(container.querySelectorAll("img")).toHaveLength(1));
    expect(container.querySelector("img")!.getAttribute("src")).toBe(AVATAR);
    expect(container.querySelectorAll('[data-slot="avatar"]')).toHaveLength(2);
  });
});
