import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import i18n from "../../i18n";
import SeoToolPage from "./SeoToolPage";

function renderAt(path: string, page: "video" | "audio" | "image") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={`/:lang/${page}-downloader`} element={<SeoToolPage page={page} />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SeoToolPage", () => {
  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it.each([
    ["video", "Video Downloader"],
    ["audio", "Audio Downloader"],
    ["image", "Image Downloader"],
  ] as const)("renders a single, page-specific H1 for %s", async (page, expectedHeading) => {
    renderAt(`/en/${page}-downloader`, page);
    const h1 = await screen.findByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent(expectedHeading);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("renders a distinct FAQ list that reflects only supported platforms", async () => {
    renderAt("/en/video-downloader", "video");
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByText("Which platforms are supported?")).toBeInTheDocument();
    expect(screen.getByText(/YouTube, TikTok, Instagram, and Facebook/)).toBeInTheDocument();
    expect(screen.queryByText(/Snapchat|Twitter|X\.com/i)).not.toBeInTheDocument();
  });

  it("links to the other two tools, not itself", async () => {
    renderAt("/en/video-downloader", "video");
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByRole("link", { name: "Audio Downloader" })).toHaveAttribute("href", "/en/audio-downloader");
    expect(screen.getByRole("link", { name: "Image Downloader" })).toHaveAttribute("href", "/en/image-downloader");
    expect(screen.queryByRole("link", { name: "Video Downloader" })).not.toBeInTheDocument();
  });

  it("renders in Arabic with RTL direction and a breadcrumb back to the localized home", async () => {
    renderAt("/ar/audio-downloader", "audio");
    await screen.findByRole("heading", { level: 1 });
    expect(document.documentElement.dir).toBe("rtl");
    expect(screen.getByRole("link", { name: "الرئيسية" })).toHaveAttribute("href", "/ar");
  });

  it("sets a page-specific canonical URL distinct from the homepage", async () => {
    renderAt("/en/image-downloader", "image");
    await screen.findByRole("heading", { level: 1 });
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute("href")).toBe(
      "https://loady.cc/en/image-downloader",
    );
  });

  it("attaches FAQ structured data matching the visible questions", async () => {
    renderAt("/en/video-downloader", "video");
    await screen.findByRole("heading", { level: 1 });
    const scripts = Array.from(document.head.querySelectorAll('script[type="application/ld+json"]'));
    const faqScript = scripts.map((s) => JSON.parse(s.textContent ?? "{}")).find((data) => data["@type"] === "FAQPage");
    expect(faqScript).toBeDefined();
    expect(faqScript.mainEntity[0].name).toBe("Which platforms are supported?");
  });
});
