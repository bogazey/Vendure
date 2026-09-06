import type { SeoStructuredData } from "./Seo";
import { siteOrigin } from "./urls";

/**
 * Every builder here only encodes facts already visible on the page it's
 * attached to - no fabricated ratings, review counts, prices, or platform
 * claims. See docs/SEO.md "Structured data" for the ground rules.
 */

export function websiteStructuredData(): SeoStructuredData {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "Loady",
    url: siteOrigin(),
  };
}

export function softwareApplicationStructuredData(): SeoStructuredData {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "Loady",
    applicationCategory: "MultimediaApplication",
    operatingSystem: "Web",
    url: siteOrigin(),
  };
}

export interface BreadcrumbItem {
  name: string;
  url: string;
}

export function breadcrumbStructuredData(items: BreadcrumbItem[]): SeoStructuredData {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: item.url,
    })),
  };
}

export interface FaqItem {
  question: string;
  answer: string;
}

/** Only attach this to a page whose FAQ content is genuinely visible in
 * the rendered HTML (it is, on every tool page - see SeoToolPage.tsx) -
 * never as a hidden rich-result trick. */
export function faqStructuredData(items: FaqItem[]): SeoStructuredData {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: item.answer },
    })),
  };
}
