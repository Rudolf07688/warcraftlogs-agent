import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { listGuides, saveProfileSettings, skipOnboarding } from "../../api/restClient";
import type { GuideListItem, GuideSummary, ProfileSettings } from "../../types";
import { OnboardingPrompt } from "./OnboardingPrompt";

// Feature 074: the welcome prompt's skip and the main selector, against the settings contract
// (specs/074-onboarding-profile-setup/contracts/profile-settings.md).

vi.mock("../../api/restClient", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/restClient")>()),
  listGuides: vi.fn(),
  saveProfileSettings: vi.fn(),
  skipOnboarding: vi.fn(),
}));

const PENDING: ProfileSettings = { main_class: null, main_spec: null, main_content: null, onboarding_pending: true };
const none = {} as GuideSummary;

function spec(class_name: string, class_display: string, s: string): GuideListItem {
  return { class_name, class_display, spec: s, spec_display: s, role: "dps", raid: none, mplus: none };
}

beforeEach(() => {
  vi.mocked(listGuides).mockResolvedValue({
    roster_source: "fallback",
    guides: [
      spec("Paladin", "Paladin", "Holy"),
      spec("Paladin", "Paladin", "Retribution"),
      spec("Warrior", "Warrior", "Fury"),
    ],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function renderPrompt(onChange = vi.fn()) {
  render(<OnboardingPrompt settings={PENDING} onChange={onChange} />);
  await waitFor(() => expect((screen.getByLabelText("Main class") as HTMLSelectElement).disabled).toBe(false));
  return onChange;
}

describe("OnboardingPrompt (074)", () => {
  it("skips through the server and hands back the not-pending state", async () => {
    vi.mocked(skipOnboarding).mockResolvedValue({ ...PENDING, onboarding_pending: false });
    const onChange = await renderPrompt();

    fireEvent.click(screen.getByRole("button", { name: "Skip for now" }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith({ ...PENDING, onboarding_pending: false }));
    expect(skipOnboarding).toHaveBeenCalledTimes(1);
  });

  it("saves exactly the three chosen values, offering only the chosen class's specs", async () => {
    const saved = { main_class: "Paladin", main_spec: "Holy", main_content: "both" as const };
    vi.mocked(saveProfileSettings).mockResolvedValue({ ...saved, onboarding_pending: true });
    const onChange = await renderPrompt();

    fireEvent.change(screen.getByLabelText("Main class"), { target: { value: "Paladin" } });
    const specOptions = [...(screen.getByLabelText("Main spec") as HTMLSelectElement).options].map((o) => o.value);
    expect(specOptions).toEqual(["", "Holy", "Retribution"]);
    fireEvent.change(screen.getByLabelText("Main spec"), { target: { value: "Holy" } });
    fireEvent.click(screen.getByRole("radio", { name: "Both" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onChange).toHaveBeenCalled());
    expect(vi.mocked(saveProfileSettings).mock.calls).toEqual([[saved]]);
  });

  it("drops the spec when the class changes", async () => {
    await renderPrompt();
    fireEvent.change(screen.getByLabelText("Main class"), { target: { value: "Paladin" } });
    fireEvent.change(screen.getByLabelText("Main spec"), { target: { value: "Holy" } });
    fireEvent.change(screen.getByLabelText("Main class"), { target: { value: "Warrior" } });
    expect((screen.getByLabelText("Main spec") as HTMLSelectElement).value).toBe("");
  });
});
