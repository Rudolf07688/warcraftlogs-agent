import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { ClassAvatar } from "./ClassAvatar";

// Feature 075, contract:class-avatar: without a portrait the avatar is the initials, as before
// (existing call sites pass none); with one, a lazy image covers them once it has loaded.

afterEach(cleanup);

const URL = "https://render.worldofwarcraft.com/eu/character/draenor/1/2-avatar.jpg";

describe("ClassAvatar", () => {
  it("renders the initials and no image without a portrait_url", () => {
    const { container } = render(<ClassAvatar char={{ name: "Thrall", class_name: "Shaman" }} className="size-10" />);
    expect(container.textContent).toBe("T");
    expect(container.querySelector("img")).toBeNull();
    const root = container.querySelector('[data-slot="avatar"]')!;
    expect(root.className).toContain("size-10");
    expect(root.className).toContain("border-border");
  });

  it("lays a lazy portrait over the initials and drops it if it fails", () => {
    const { container } = render(<ClassAvatar char={{ name: "Thrall", class_name: "Shaman", portrait_url: URL }} />);
    const img = container.querySelector("img")!;
    expect(img.getAttribute("src")).toBe(URL);
    expect(img.getAttribute("loading")).toBe("lazy");
    expect(img.className).toContain("opacity-0"); // initials until it has loaded
    expect(container.textContent).toBe("T");
    fireEvent.load(img);
    expect(img.className).toContain("opacity-100");
    fireEvent.error(img);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toBe("T");
  });

  it("never puts another host in img src", () => {
    for (const bad of ["javascript:alert(1)", "https://evil.example/x.jpg", "http://render.worldofwarcraft.com/x.jpg"]) {
      const { container, unmount } = render(<ClassAvatar char={{ name: "T", class_name: null, portrait_url: bad }} />);
      expect(container.querySelector("img")).toBeNull();
      unmount();
    }
  });
});
