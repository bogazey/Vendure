import { describe, expect, it } from "vitest";
import { resolveTheme } from "./theme";

describe("resolveTheme", () => {
  it("resolves an explicit light preference to light", () => {
    expect(resolveTheme("light")).toBe("light");
  });

  it("resolves an explicit dark preference to dark", () => {
    expect(resolveTheme("dark")).toBe("dark");
  });

  it("falls back to dark for 'system' when no window/matchMedia is available", () => {
    // This test runs in a Node (non-DOM) environment, so `window` doesn't
    // exist - resolveTheme's systemPrefersDark() must not throw, and should
    // fall back to a safe default (dark) rather than crash.
    expect(resolveTheme("system")).toBe("dark");
  });
});
