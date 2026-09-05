import { describe, expect, it } from "vitest";
import { resolveTheme } from "./theme";

describe("resolveTheme", () => {
  it("resolves an explicit light preference to light", () => {
    expect(resolveTheme("light")).toBe("light");
  });

  it("resolves an explicit dark preference to dark", () => {
    expect(resolveTheme("dark")).toBe("dark");
  });

  it("resolves 'system' to dark - the brand identity is fixed dark, not OS-tracking", () => {
    expect(resolveTheme("system")).toBe("dark");
  });
});
