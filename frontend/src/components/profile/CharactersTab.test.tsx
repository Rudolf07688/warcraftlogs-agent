import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { getPortraits } from "../../api/portraits";
import { getProfile } from "../../api/restClient";
import { resetPortraitsCache } from "../../hooks/usePortraits";
import type { Character, Profile } from "../../types";
import { CharactersTab } from "./CharactersTab";

// Feature 075 (sc-364): the profile's character list shows each character's portrait, from its
// own request; a character without one keeps the initials.

vi.mock("../../api/restClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/restClient")>()),
  getProfile: vi.fn(),
}));
vi.mock("../../api/portraits", () => ({ getPortraits: vi.fn() }));

const AVATAR = "https://render.worldofwarcraft.com/eu/character/draenor/1/2-avatar.jpg";

function char(id: string, name: string, role: Character["role"]): Character {
  return {
    id,
    role,
    name,
    server: "Draenor",
    region: "EU",
    class_name: "Warrior",
    active_spec: null,
    raid_role: null,
    effective_role: null,
    guides: { raid: "none", mplus: "none" },
  };
}

const PROFILE: Profile = { own: [char("c1", "Brakk", "self")], own_limit: 3, friends: [char("c2", "Ula", "friend")], guild: null };

beforeEach(() => {
  resetPortraitsCache();
  vi.mocked(getProfile).mockResolvedValue(PROFILE);
  vi.mocked(getPortraits).mockResolvedValue({
    portraits: [
      { character_id: "c1", name: "Brakk", server: "Draenor", region: "eu", class_name: "Warrior", portrait_url: AVATAR },
      { character_id: "c2", name: "Ula", server: "Draenor", region: "eu", class_name: "Warrior", portrait_url: null },
    ],
  });
});
afterEach(cleanup);

describe("CharactersTab portraits", () => {
  it("shows the own character's portrait and the friend's initials", async () => {
    const { container, findByText } = render(<CharactersTab />);
    await findByText("Brakk");
    await waitFor(() => expect(container.querySelectorAll("img")).toHaveLength(1));
    expect(container.querySelector("img")!.getAttribute("src")).toBe(AVATAR);
    expect(getPortraits).toHaveBeenCalledTimes(1);
  });
});
