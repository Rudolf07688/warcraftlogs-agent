import { describe, expect, it } from "vitest";
import { afterLoginPath, CHAT_HOME, PROFILE_PATH, safeInternalPath } from "./redirect";

describe("safeInternalPath (074)", () => {
  it.each([
    "//evil.example",
    "//evil.example/app",
    "/\\evil.example",
    "\\\\evil.example",
    "javascript:alert(1)",
    "https://evil.example/app",
    "/\t/evil.example",
    "/\n/evil.example",
    "",
    null,
    undefined,
    42,
    { pathname: "/app" },
  ])("sends %j to the chat home", (from) => {
    expect(safeInternalPath(from)).toBe(CHAT_HOME);
  });

  it.each(["/app", "/app/raids/a1B2c3D4", "/admin/users", "/profile"])("keeps the in-app path %s", (from) => {
    expect(safeInternalPath(from)).toBe(from);
  });
});

describe("afterLoginPath (074)", () => {
  it("sends a pending workspace headed home to the profile page", () => {
    expect(afterLoginPath("/app", true)).toBe(PROFILE_PATH);
    expect(afterLoginPath(undefined, true)).toBe(PROFILE_PATH);
    expect(afterLoginPath("//evil.example", true)).toBe(PROFILE_PATH);
  });

  it("honours a specific in-app destination, and goes home when not pending", () => {
    expect(afterLoginPath("/admin/users", true)).toBe("/admin/users");
    expect(afterLoginPath("/app", false)).toBe(CHAT_HOME);
    expect(afterLoginPath("//evil.example", false)).toBe(CHAT_HOME);
  });
});
