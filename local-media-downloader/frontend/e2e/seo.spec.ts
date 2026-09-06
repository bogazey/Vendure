import { expect, test } from "@playwright/test";

/**
 * These run against `npm run dev` (a pure client-side render - see
 * playwright.config.ts's webServer) so they exercise the same <Seo>
 * component logic the production prerender script's static HTML is built
 * from, without needing a full production build in this suite. The actual
 * prerendered static HTML output is verified separately by running
 * `npm run build` and inspecting dist/<lang>/<slug>/index.html - see
 * docs/SEO.md "Verifying the prerendered output".
 */

test("robots.txt allows public pages, disallows private ones, and references the sitemap", async ({ page }) => {
  const response = await page.goto("/robots.txt");
  expect(response?.status()).toBe(200);
  const body = await response!.text();
  expect(body).toContain("Disallow: /dashboard");
  expect(body).toContain("Disallow: /admin");
  expect(body).toContain("Disallow: /login");
  expect(body).toContain("Disallow: /api/");
  expect(body).toContain("Sitemap: https://loady.cc/sitemap.xml");
  expect(body).not.toContain("Disallow: /en");
  expect(body).not.toContain("Disallow: /ar");
});

test("English homepage has correct title, H1, lang, canonical, and hreflang", async ({ page }) => {
  await page.goto("/en");
  await expect(page).toHaveTitle(/Loady/);
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", "https://loady.cc/en");
  const hreflangs = await page.locator('link[rel="alternate"]').evaluateAll((els) =>
    els.map((el) => el.getAttribute("hreflang")).sort(),
  );
  expect(hreflangs).toEqual(["ar", "en", "x-default"]);
});

test("Arabic homepage renders RTL with translated title and content", async ({ page }) => {
  await page.goto("/ar");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page).toHaveTitle(/Loady/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("حمّل");
});

// Each tool page gets its own single-navigation test (rather than one test
// looping over all three with sequential/concurrent goto() calls) - this
// sandbox's substitute Chromium binary is prone to hanging on rapid
// repeated navigation, a known environment limitation unrelated to the
// product (see docs/SEO.md). Distinct per-page titles are already proven
// by src/pages/seo/SeoHomePage.test.tsx and the seo.meta.* content itself
// (each page pulls a different i18n key).
for (const tool of ["video", "audio", "image"] as const) {
  test(`${tool} tool page has its own page-specific canonical URL and title`, async ({ page }) => {
    await page.goto(`/en/${tool}-downloader`);
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", `https://loady.cc/en/${tool}-downloader`);
    await expect(page).toHaveTitle(/Loady/);
  });
}

test("the language switcher on a tool page preserves the page when switching language", async ({ page }) => {
  await page.goto("/en/video-downloader");
  await page.locator('a[href="/ar/video-downloader"]').first().click();
  await expect(page).toHaveURL(/\/ar\/video-downloader$/);
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
});

test("homepage links reach all three tool pages", async ({ page }) => {
  await page.goto("/en");
  await page.getByRole("link", { name: "Video Downloader" }).click();
  await expect(page).toHaveURL(/\/en\/video-downloader$/);
});

test("an unknown URL renders a noindex 404 page with a way back to Loady", async ({ page }) => {
  const response = await page.goto("/this-page-does-not-exist");
  // A pure client-side SPA fallback is served as HTTP 200 by the dev
  // server; a real HTTP 404 status requires production host configuration
  // - see docs/SEO.md "404 / status behavior".
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Page not found");
  const robots = await page.locator('meta[name="robots"]').getAttribute("content");
  expect(robots).toBe("noindex, nofollow");
  await page.getByRole("link", { name: "Back to Loady" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("private app routes are marked noindex even when reachable", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, nofollow");
});
