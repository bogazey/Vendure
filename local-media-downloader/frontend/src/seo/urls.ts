/**
 * Single source of truth for Loady's bilingual, indexable public SEO
 * pages - the exact URL set that appears in the sitemap, the prerender
 * script's build list, hreflang alternates, and internal navigation.
 *
 * Adding a new bilingual SEO page means adding one entry to SEO_PAGES
 * (plus writing its content and routing it in App.tsx) - see
 * docs/SEO.md, "How to add a new bilingual SEO page".
 */

export const SUPPORTED_SEO_LANGUAGES = ["en", "ar"] as const;
export type SeoLanguage = (typeof SUPPORTED_SEO_LANGUAGES)[number];

export function isSeoLanguage(value: string | undefined): value is SeoLanguage {
  return value === "en" || value === "ar";
}

export type SeoPageKey = "home" | "video" | "audio" | "image";

/** Empty slug means the page lives at the bare /:lang root. */
export const SEO_PAGE_SLUGS: Record<SeoPageKey, string> = {
  home: "",
  video: "video-downloader",
  audio: "audio-downloader",
  image: "image-downloader",
};

export const SEO_PAGES: SeoPageKey[] = ["home", "video", "audio", "image"];

/**
 * Production origin for absolute canonical/hreflang/OG URLs. These tags
 * are only meaningful once deployed, so a fixed production origin (rather
 * than window.location.origin) is used even in local/dev builds -
 * VITE_SITE_URL can override it for a staging domain without code changes.
 */
export const PRODUCTION_ORIGIN = "https://loady.cc";

export function siteOrigin(): string {
  const configured = import.meta.env.VITE_SITE_URL?.trim();
  return configured ? configured.replace(/\/$/, "") : PRODUCTION_ORIGIN;
}

/** Path only, e.g. "/en" or "/ar/video-downloader" - no leading domain. */
export function seoPath(lang: SeoLanguage, page: SeoPageKey): string {
  const slug = SEO_PAGE_SLUGS[page];
  return slug ? `/${lang}/${slug}` : `/${lang}`;
}

/** Absolute canonical/hreflang/OG URL for one localized SEO page. */
export function seoUrl(lang: SeoLanguage, page: SeoPageKey): string {
  return `${siteOrigin()}${seoPath(lang, page)}`;
}

export interface HreflangAlternate {
  hreflang: SeoLanguage | "x-default";
  href: string;
}

/**
 * Reciprocal alternate-language links for one page: every supported
 * language's version of this exact page, plus x-default pointing at the
 * English version (the documented fallback for unsupported languages -
 * see src/i18n/index.ts's fallbackLng: "en").
 */
export function hreflangAlternates(page: SeoPageKey): HreflangAlternate[] {
  const alternates: HreflangAlternate[] = SUPPORTED_SEO_LANGUAGES.map((lang) => ({
    hreflang: lang,
    href: seoUrl(lang, page),
  }));
  alternates.push({ hreflang: "x-default", href: seoUrl("en", page) });
  return alternates;
}

/** The other supported language's version of the same page - used by the
 * locale-aware language switcher on SEO pages to preserve context instead
 * of always bouncing to the other language's homepage. */
export function siblingSeoPath(currentLang: SeoLanguage, page: SeoPageKey): string {
  const other: SeoLanguage = currentLang === "en" ? "ar" : "en";
  return seoPath(other, page);
}

export interface SeoRoute {
  lang: SeoLanguage;
  page: SeoPageKey;
  path: string;
  url: string;
}

/** Every indexable (lang, page) combination - the flat list the sitemap
 * generator, the prerender script, and tests all iterate over. */
export function allSeoRoutes(): SeoRoute[] {
  const routes: SeoRoute[] = [];
  for (const page of SEO_PAGES) {
    for (const lang of SUPPORTED_SEO_LANGUAGES) {
      routes.push({ lang, page, path: seoPath(lang, page), url: seoUrl(lang, page) });
    }
  }
  return routes;
}
