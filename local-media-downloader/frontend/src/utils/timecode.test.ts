import { describe, expect, it } from "vitest";
import { parseTimecode } from "./timecode";

describe("parseTimecode", () => {
  it("parses MM:SS", () => {
    expect(parseTimecode("02:30")).toBe(150);
  });

  it("parses HH:MM:SS", () => {
    expect(parseTimecode("01:02:03")).toBe(3723);
  });

  it("parses zero", () => {
    expect(parseTimecode("00:00")).toBe(0);
  });

  it("trims whitespace", () => {
    expect(parseTimecode("  01:00  ")).toBe(60);
  });

  it("throws on malformed input", () => {
    expect(() => parseTimecode("not a time")).toThrow();
  });

  it("throws on out-of-range seconds", () => {
    expect(() => parseTimecode("00:99")).toThrow();
  });

  it("throws when missing a colon", () => {
    expect(() => parseTimecode("12345")).toThrow();
  });
});
