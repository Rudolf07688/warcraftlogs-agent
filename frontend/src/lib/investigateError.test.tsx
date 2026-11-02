import { describe, expect, it } from "vitest";
import { ApiError } from "../api/restClient";
import { investigateErrorMessage } from "./investigateError";

describe("investigateErrorMessage", () => {
  it("names the per-user limit for a 429", () => {
    const err = new ApiError(429, "Too many investigations. Slow down.", "rate_limited");
    expect(investigateErrorMessage(err)).toMatch(/Too many investigations/);
    expect(investigateErrorMessage(err)).not.toMatch(/backend/);
  });

  it("keeps the backend hint for anything else", () => {
    expect(investigateErrorMessage(new ApiError(500, "boom"))).toMatch(/Is the backend up/);
    expect(investigateErrorMessage(new TypeError("Failed to fetch"))).toMatch(/Is the backend up/);
    expect(investigateErrorMessage(null)).toMatch(/Is the backend up/);
  });
});
