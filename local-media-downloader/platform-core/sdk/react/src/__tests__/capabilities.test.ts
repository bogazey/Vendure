import { describe, expect, it } from "vitest";
import { hasCapability } from "../capabilities";

describe("hasCapability", () => {
  it("returns false for a missing key (fail closed)", () => {
    expect(hasCapability({}, "x")).toBe(false);
    expect(hasCapability(null, "x")).toBe(false);
    expect(hasCapability(undefined, "x")).toBe(false);
  });

  it("passes through a boolean value", () => {
    expect(hasCapability({ x: true }, "x")).toBe(true);
    expect(hasCapability({ x: false }, "x")).toBe(false);
  });

  it("compares an integer against atLeast", () => {
    expect(hasCapability({ x: 5 }, "x", 10)).toBe(false);
    expect(hasCapability({ x: 10 }, "x", 10)).toBe(true);
    expect(hasCapability({ x: 20 }, "x", 10)).toBe(true);
  });

  it("treats -1 as unlimited, always satisfying atLeast", () => {
    expect(hasCapability({ x: -1 }, "x", 999999)).toBe(true);
  });

  it("treats a truthy string/enum value as granted when no atLeast is given", () => {
    expect(hasCapability({ tier: "gold" }, "tier")).toBe(true);
    expect(hasCapability({ tier: "" }, "tier")).toBe(false);
  });
});
