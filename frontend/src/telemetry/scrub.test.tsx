import { describe, expect, it } from "vitest";
import type { TransportItem } from "@grafana/faro-react";
import { scrubItem, scrubString } from "./scrub";

// Feature 057 (SEC-006): a token in a URL's query or fragment never leaves the browser.

describe("scrubString", () => {
  it.each([
    ["http://localhost:5173/reset-password#token=abc123", "http://localhost:5173/reset-password"],
    ["http://localhost:5173/accept-invite?token=abc123&x=1", "http://localhost:5173/accept-invite"],
    ["/reset-password#token=abc123", "/reset-password"],
    ["https://h/p?a=1#frag", "https://h/p"],
    ["http://localhost:5173/app", "http://localhost:5173/app"],
    ["/api/conversations", "/api/conversations"],
  ])("cuts the URL %s", (input, expected) => {
    expect(scrubString(input)).toBe(expected);
  });

  it("cuts a URL inside a longer message and leaves the rest", () => {
    expect(scrubString("Failed to load http://x/reset#token=abc123 (status 404)")).toBe(
      "Failed to load http://x/reset (status 404)",
    );
  });

  it("leaves text that is not a URL alone", () => {
    expect(scrubString("what? #1 raid")).toBe("what? #1 raid");
  });
});

describe("scrubItem", () => {
  const item = {
    type: "event",
    payload: { name: "faro.navigation", attributes: { toUrl: "/reset-password#token=SECRET", fromRoute: "/login" } },
    meta: { page: { url: "http://localhost:5173/reset-password#token=SECRET" }, session: { id: "s1" } },
  } as unknown as TransportItem;

  it("cleans the page meta and the event attributes", () => {
    const out = JSON.stringify(scrubItem(item));
    expect(out).not.toContain("SECRET");
    expect(out).not.toContain("token=");
    expect(scrubItem(item).meta.page?.url).toBe("http://localhost:5173/reset-password");
  });

  it("cleans the URL attributes of a recorded span (OTLP JSON)", () => {
    const trace = {
      type: "traces",
      payload: {
        resourceSpans: [
          {
            scopeSpans: [
              {
                spans: [
                  {
                    name: "documentLoad",
                    attributes: [
                      { key: "http.url", value: { stringValue: "http://localhost:5173/accept-invite?token=SECRET" } },
                      { key: "http.status_code", value: { intValue: 200 } },
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
      meta: {},
    } as unknown as TransportItem;
    const out = scrubItem(trace);
    expect(JSON.stringify(out)).not.toContain("SECRET");
    expect(JSON.stringify(out)).toContain("http://localhost:5173/accept-invite");
    expect(JSON.stringify(out)).toContain("200");
    expect(Array.isArray((out.payload as { resourceSpans: unknown }).resourceSpans)).toBe(true); // shape kept
  });

  it("does not change the item it was given", () => {
    scrubItem(item);
    expect(item.meta.page?.url).toContain("#token=SECRET");
  });
});
