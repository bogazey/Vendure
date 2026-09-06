import { useEffect } from "react";
import type { HreflangAlternate, SeoLanguage } from "./urls";

export interface SeoStructuredData {
  "@context": "https://schema.org";
  "@type": string;
  [key: string]: unknown;
}

export interface SeoProps {
  /** Absolute canonical URL for this exact page (see src/seo/urls.ts). */
  url: string;
  title: string;
  description: string;
  lang?: SeoLanguage;
  /** Reciprocal alternate-language links, see hreflangAlternates(). Omit
   * for pages that intentionally have no localized counterpart. */
  hreflang?: HreflangAlternate[];
  ogTitle?: string;
  ogDescription?: string;
  /** Absolute URL to a branded social-preview image. Omitted rather than
   * pointing at a placeholder if no suitable asset exists - see docs/SEO.md. */
  ogImage?: string;
  /** True for pages that must never be indexed (auth, app, admin, 404). */
  noindex?: boolean;
  structuredData?: SeoStructuredData | SeoStructuredData[];
}

/**
 * Centralized SEO metadata for one page - the single place that ever
 * writes <title>, meta description, canonical, hreflang, Open Graph,
 * Twitter Card, and JSON-LD tags, instead of scattering hard-coded tags
 * across page components.
 *
 * Two runtimes read this component's output:
 * 1. A real browser: the effect below mutates the live document head and
 *    restores the previous (index.html default) values on unmount, so
 *    navigating away from an SEO page never leaves stale tags behind.
 * 2. scripts/prerender.mjs (build-time, Node, ReactDOMServer.renderToStaticMarkup):
 *    effects never run during static rendering, so that script instead
 *    reads `lastRenderedSeo` - set synchronously in this component's
 *    render body, which SSR/static rendering *does* execute - immediately
 *    after rendering each page, and builds the static <head> from it. This
 *    is the same "collect head data during render" technique classic
 *    react-helmet used, deliberately kept to a single well-documented
 *    module-level slot rather than pulled in as a dependency.
 */
export let lastRenderedSeo: SeoProps | null = null;

const MANAGED_ATTR = "data-seo-managed";

function upsertMeta(attr: "name" | "property", key: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    el.setAttribute(MANAGED_ATTR, "true");
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function removeManagedTags() {
  document.head.querySelectorAll(`[${MANAGED_ATTR}]`).forEach((el) => el.remove());
}

export function Seo(props: SeoProps): null {
  // Executes during render on both the client and in renderToStaticMarkup -
  // see the module doc comment above for why this assignment (not an
  // effect) is what the prerender script actually depends on.
  lastRenderedSeo = props;

  useEffect(() => {
    const previousTitle = document.title;
    const previousDescription = document.head.querySelector('meta[name="description"]')?.getAttribute("content") ?? null;
    const previousOgTitle = document.head.querySelector('meta[property="og:title"]')?.getAttribute("content") ?? null;
    const previousOgDescription = document.head.querySelector('meta[property="og:description"]')?.getAttribute("content") ?? null;

    document.title = props.title;
    upsertMeta("name", "description", props.description);
    upsertMeta("property", "og:title", props.ogTitle ?? props.title);
    upsertMeta("property", "og:description", props.ogDescription ?? props.description);
    upsertMeta("property", "og:url", props.url);
    upsertMeta("property", "og:type", "website");
    if (props.ogImage) upsertMeta("property", "og:image", props.ogImage);
    upsertMeta("name", "twitter:card", props.ogImage ? "summary_large_image" : "summary");
    upsertMeta("name", "twitter:title", props.ogTitle ?? props.title);
    upsertMeta("name", "twitter:description", props.ogDescription ?? props.description);
    if (props.ogImage) upsertMeta("name", "twitter:image", props.ogImage);

    const canonical = document.createElement("link");
    canonical.rel = "canonical";
    canonical.href = props.url;
    canonical.setAttribute(MANAGED_ATTR, "true");
    document.head.appendChild(canonical);

    for (const alt of props.hreflang ?? []) {
      const link = document.createElement("link");
      link.rel = "alternate";
      link.hreflang = alt.hreflang;
      link.href = alt.href;
      link.setAttribute(MANAGED_ATTR, "true");
      document.head.appendChild(link);
    }

    if (props.noindex) {
      upsertMeta("name", "robots", "noindex, nofollow");
    }

    const structuredDataEntries = Array.isArray(props.structuredData)
      ? props.structuredData
      : props.structuredData
        ? [props.structuredData]
        : [];
    for (const entry of structuredDataEntries) {
      const script = document.createElement("script");
      script.type = "application/ld+json";
      script.setAttribute(MANAGED_ATTR, "true");
      script.textContent = JSON.stringify(entry);
      document.head.appendChild(script);
    }

    return () => {
      removeManagedTags();
      document.title = previousTitle;
      if (previousDescription !== null) upsertMeta("name", "description", previousDescription);
      if (previousOgTitle !== null) upsertMeta("property", "og:title", previousOgTitle);
      if (previousOgDescription !== null) upsertMeta("property", "og:description", previousOgDescription);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.url, props.title, props.description, props.noindex, JSON.stringify(props.hreflang), JSON.stringify(props.structuredData)]);

  return null;
}
