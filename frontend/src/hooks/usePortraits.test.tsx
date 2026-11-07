import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { getPortraits } from "../api/portraits";
import { resetPortraitsCache, usePortraits } from "./usePortraits";

// Feature 075: one portraits request for every avatar on screen; a failure is "no portraits".

vi.mock("../api/portraits", () => ({ getPortraits: vi.fn() }));
const fetchPortraits = vi.mocked(getPortraits);

const AVATAR = "https://render.worldofwarcraft.com/us/character/area-52/1/2-avatar.jpg";
const THRALL = { character_id: "c1", name: "Thrall", server: "Kel'Thuzad", region: "us", class_name: "Shaman", portrait_url: AVATAR };

function Probe({ id }: { id: string }) {
  const p = usePortraits();
  return (
    <span data-testid={id}>
      {p.byId("c1")?.portrait_url ?? "none"}|{p.byIdentity("THRALL", "kelthuzad", "US")?.portrait_url ?? "none"}
    </span>
  );
}

beforeEach(() => {
  fetchPortraits.mockReset();
  resetPortraitsCache();
});
afterEach(cleanup);

describe("usePortraits", () => {
  it("shares one request between avatars and matches by id or identity", async () => {
    fetchPortraits.mockResolvedValue({ portraits: [THRALL] });
    const { getByTestId } = render(
      <>
        <Probe id="a" />
        <Probe id="b" />
        <Probe id="c" />
      </>,
    );
    await waitFor(() => expect(getByTestId("c").textContent).toBe(`${AVATAR}|${AVATAR}`));
    expect(getByTestId("a").textContent).toBe(`${AVATAR}|${AVATAR}`);
    expect(fetchPortraits).toHaveBeenCalledTimes(1);
  });

  it("leaves every avatar on its initials when the request fails", async () => {
    fetchPortraits.mockRejectedValue(new Error("502"));
    const { getByTestId } = render(<Probe id="a" />);
    await waitFor(() => expect(fetchPortraits).toHaveBeenCalledTimes(1));
    expect(getByTestId("a").textContent).toBe("none|none");
  });
});
