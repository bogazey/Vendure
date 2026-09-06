import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import i18n from "../../i18n";
import SeoHomePage from "./SeoHomePage";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/:lang" element={<SeoHomePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SeoHomePage", () => {
  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("renders the English homepage with a single H1 and correct document language/direction", async () => {
    renderAt("/en");
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Download video, audio, and images");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
    expect(document.title).toContain("Loady");
  });

  it("renders the Arabic homepage in RTL with translated content", async () => {
    renderAt("/ar");
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("حمّل الفيديو والصوت والصور");
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
  });

  it("links to all three tool pages in the current language", async () => {
    renderAt("/en");
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByRole("link", { name: /Video Downloader/ })).toHaveAttribute("href", "/en/video-downloader");
    expect(screen.getByRole("link", { name: /Audio Downloader/ })).toHaveAttribute("href", "/en/audio-downloader");
    expect(screen.getByRole("link", { name: /Image Downloader/ })).toHaveAttribute("href", "/en/image-downloader");
  });

  it("renders NotFound content for an unsupported language segment", async () => {
    renderAt("/fr");
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(/not found|غير موجودة/i);
  });

  it("sets the canonical URL and reciprocal hreflang alternates", async () => {
    renderAt("/en");
    await screen.findByRole("heading", { level: 1 });
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute("href")).toBe("https://loady.cc/en");
    const hreflangs = Array.from(document.head.querySelectorAll('link[rel="alternate"]')).map((el) => el.getAttribute("hreflang"));
    expect(hreflangs.sort()).toEqual(["ar", "en", "x-default"]);
  });
});
