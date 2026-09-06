import { describe, expect, it } from "vitest";
import {
  PRODUCTION_ORIGIN,
  SEO_PAGES,
  SUPPORTED_SEO_LANGUAGES,
  allSeoRoutes,
  hreflangAlternates,
  isSeoLanguage,
  seoPath,
  seoUrl,
  siblingSeoPath,
} from "./urls";

describe("seoPath / seoUrl", () => {
  it("builds the bare /:lang path for the home page", () => {
    expect(seoPath("en", "home")).toBe("/en");
    expect(seoPath("ar", "home")).toBe("/ar");
  });

  it("builds /:lang/:slug for tool pages", () => {
    expect(seoPath("en", "video")).toBe("/en/video-downloader");
    expect(seoPath("ar", "audio")).toBe("/ar/audio-downloader");
    expect(seoPath("en", "image")).toBe("/en/image-downloader");
  });

  it("builds an absolute canonical URL against the production origin", () => {
    expect(seoUrl("en", "video")).toBe(`${PRODUCTION_ORIGIN}/en/video-downloader`);
  });
});

describe("isSeoLanguage", () => {
  it("accepts only the two supported languages", () => {
    expect(isSeoLanguage("en")).toBe(true);
    expect(isSeoLanguage("ar")).toBe(true);
    expect(isSeoLanguage("fr")).toBe(false);
    expect(isSeoLanguage(undefined)).toBe(false);
    expect(isSeoLanguage("")).toBe(false);
  });
});

describe("hreflangAlternates", () => {
  it("returns a reciprocal en/ar pair plus x-default pointing at English", () => {
    const alternates = hreflangAlternates("video");
    expect(alternates).toEqual([
      { hreflang: "en", href: `${PRODUCTION_ORIGIN}/en/video-downloader` },
      { hreflang: "ar", href: `${PRODUCTION_ORIGIN}/ar/video-downloader` },
      { hreflang: "x-default", href: `${PRODUCTION_ORIGIN}/en/video-downloader` },
    ]);
  });

  it("never points hreflang at a different page than the one it's declared on", () => {
    for (const page of SEO_PAGES) {
      for (const alt of hreflangAlternates(page)) {
        expect(alt.href).toContain(page === "home" ? "" : page === "video" ? "video-downloader" : "");
      }
    }
  });
});

describe("siblingSeoPath", () => {
  it("returns the other language's URL for the same page", () => {
    expect(siblingSeoPath("en", "audio")).toBe("/ar/audio-downloader");
    expect(siblingSeoPath("ar", "audio")).toBe("/en/audio-downloader");
  });
});

describe("allSeoRoutes", () => {
  it("enumerates every language x page combination exactly once", () => {
    const routes = allSeoRoutes();
    expect(routes).toHaveLength(SUPPORTED_SEO_LANGUAGES.length * SEO_PAGES.length);

    const seen = new Set<string>();
    for (const route of routes) {
      expect(seen.has(route.path)).toBe(false);
      seen.add(route.path);
      expect(route.url).toBe(`${PRODUCTION_ORIGIN}${route.path}`);
    }
  });

  it("never includes a private/application route", () => {
    const routes = allSeoRoutes();
    const forbidden = ["/dashboard", "/admin", "/account", "/settings", "/billing", "/login", "/signup", "/api"];
    for (const route of routes) {
      for (const bad of forbidden) {
        expect(route.path.startsWith(bad)).toBe(false);
      }
    }
  });
});
