import { describe, expect, it } from "vitest";
import { formatBytes, formatDuration, formatEta, formatSpeed } from "./format";

describe("formatBytes", () => {
  it("handles null/undefined as em dash", () => {
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(undefined)).toBe("—");
  });

  it("formats zero", () => {
    expect(formatBytes(0)).toBe("0 B");
  });

  it("formats bytes without decimals", () => {
    expect(formatBytes(512)).toBe("512 B");
  });

  it("formats kilobytes", () => {
    expect(formatBytes(2048)).toBe("2.0 KB");
  });

  it("formats megabytes", () => {
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});

describe("formatSpeed", () => {
  it("handles null as em dash", () => {
    expect(formatSpeed(null)).toBe("—");
  });

  it("appends /s to a byte rate", () => {
    expect(formatSpeed(1024)).toBe("1.0 KB/s");
  });
});

describe("formatEta", () => {
  it("handles null as em dash", () => {
    expect(formatEta(null)).toBe("—");
  });

  it("formats sub-minute durations as seconds only", () => {
    expect(formatEta(45)).toBe("45s");
  });

  it("formats minutes and seconds", () => {
    expect(formatEta(125)).toBe("2m 5s");
  });
});

describe("formatDuration", () => {
  it("handles null as em dash", () => {
    expect(formatDuration(null)).toBe("—");
  });

  it("formats under an hour as M:SS", () => {
    expect(formatDuration(65)).toBe("1:05");
  });

  it("formats an hour or more as H:MM:SS", () => {
    expect(formatDuration(3661)).toBe("1:01:01");
  });
});
