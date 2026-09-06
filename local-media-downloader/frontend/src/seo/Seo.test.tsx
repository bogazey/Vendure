import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Seo } from "./Seo";

function meta(name: string): string | null {
  return document.head.querySelector(`meta[name="${name}"]`)?.getAttribute("content") ?? null;
}

function ogMeta(property: string): string | null {
  return document.head.querySelector(`meta[property="${property}"]`)?.getAttribute("content") ?? null;
}

describe("Seo", () => {
  it("sets title, description, canonical, and Open Graph tags", () => {
    render(
      <Seo
        url="https://loady.cc/en/video-downloader"
        title="Video Downloader | Loady"
        description="Download video for offline viewing."
      />,
    );

    expect(document.title).toBe("Video Downloader | Loady");
    expect(meta("description")).toBe("Download video for offline viewing.");
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute("href")).toBe(
      "https://loady.cc/en/video-downloader",
    );
    expect(ogMeta("og:title")).toBe("Video Downloader | Loady");
    expect(ogMeta("og:url")).toBe("https://loady.cc/en/video-downloader");
  });

  it("renders reciprocal hreflang alternate links", () => {
    render(
      <Seo
        url="https://loady.cc/en"
        title="Home"
        description="Home"
        hreflang={[
          { hreflang: "en", href: "https://loady.cc/en" },
          { hreflang: "ar", href: "https://loady.cc/ar" },
          { hreflang: "x-default", href: "https://loady.cc/en" },
        ]}
      />,
    );

    const links = Array.from(document.head.querySelectorAll('link[rel="alternate"]')).map((el) => ({
      hreflang: el.getAttribute("hreflang"),
      href: el.getAttribute("href"),
    }));
    expect(links).toEqual([
      { hreflang: "en", href: "https://loady.cc/en" },
      { hreflang: "ar", href: "https://loady.cc/ar" },
      { hreflang: "x-default", href: "https://loady.cc/en" },
    ]);
  });

  it("never leaves more than one canonical tag in the document at a time", () => {
    const { rerender } = render(<Seo url="https://loady.cc/en" title="A" description="A" />);
    rerender(<Seo url="https://loady.cc/ar" title="B" description="B" />);
    expect(document.head.querySelectorAll('link[rel="canonical"]')).toHaveLength(1);
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute("href")).toBe("https://loady.cc/ar");
  });

  it("sets a noindex robots meta tag when noindex is true", () => {
    render(<Seo url="https://loady.cc/login" title="Sign in" description="Sign in" noindex />);
    expect(meta("robots")).toBe("noindex, nofollow");
  });

  it("does not set a robots meta tag for an indexable page", () => {
    render(<Seo url="https://loady.cc/en" title="Home" description="Home" />);
    expect(meta("robots")).toBeNull();
  });

  it("emits one JSON-LD script per structured data entry", () => {
    render(
      <Seo
        url="https://loady.cc/en"
        title="Home"
        description="Home"
        structuredData={[
          { "@context": "https://schema.org", "@type": "WebSite", name: "Loady", url: "https://loady.cc" },
          { "@context": "https://schema.org", "@type": "SoftwareApplication", name: "Loady" },
        ]}
      />,
    );
    const scripts = document.head.querySelectorAll('script[type="application/ld+json"]');
    expect(scripts).toHaveLength(2);
    expect(JSON.parse(scripts[0].textContent ?? "{}")["@type"]).toBe("WebSite");
    expect(JSON.parse(scripts[1].textContent ?? "{}")["@type"]).toBe("SoftwareApplication");
  });

  it("restores the previous description on unmount instead of leaking it to the next page", () => {
    const original = document.createElement("meta");
    original.setAttribute("name", "description");
    original.setAttribute("content", "Loady default description");
    document.head.appendChild(original);

    const { unmount } = render(<Seo url="https://loady.cc/en" title="Home" description="Home-specific description" />);
    expect(meta("description")).toBe("Home-specific description");

    unmount();
    expect(meta("description")).toBe("Loady default description");
    expect(document.head.querySelector('link[rel="canonical"]')).toBeNull();

    original.remove();
  });
});
