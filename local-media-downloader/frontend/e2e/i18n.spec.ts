import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

async function mockAppShellApi(page: Page) {
  await page.route("http://127.0.0.1:8000/api/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith("/account")) {
      await route.fulfill({ status: 204 });
      return;
    }
    if (pathname.endsWith("/settings")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ theme: "system" }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ffmpeg_available: true }) });
  });
}

test("switches languages immediately and persists Arabic", async ({ page }) => {
  await mockAppShellApi(page);
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  await page.goto("/");
  await page.getByRole("button", { name: "العربية" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("حرية الاحتفاظ");

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await page.getByRole("button", { name: "EN" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  expect(consoleErrors).toEqual([]);
});

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
]) {
  for (const language of ["en", "ar"] as const) {
    test(`${language} has no horizontal overflow at ${viewport.width}px`, async ({ page }) => {
      await mockAppShellApi(page);
      const consoleErrors: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });
      await page.setViewportSize(viewport);
      await page.addInitScript((lang) => localStorage.setItem("loady-language", lang), language);

      for (const path of ["/", "/pricing", "/login"]) {
        await page.goto(path);
        await expect(page.locator("html")).toHaveAttribute("dir", language === "ar" ? "rtl" : "ltr");
        const overflow = await page.evaluate(() => ({
          body: document.body.scrollWidth - document.body.clientWidth,
          root: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        }));
        expect(overflow.body, `${language} body overflow on ${path}`).toBeLessThanOrEqual(0);
        expect(overflow.root, `${language} root overflow on ${path}`).toBeLessThanOrEqual(0);
        if (path === "/pricing") {
          await expect(page.getByRole("heading", { level: 1 })).toHaveText(language === "ar" ? "أسعار واضحة وبسيطة" : "Simple, transparent pricing");
        }
        if (path === "/login") {
          await expect(page.getByLabel(language === "ar" ? "البريد الإلكتروني" : "Email")).toBeVisible();
        }
      }

      if (viewport.width === 390) {
        await page.getByRole("button", { name: language === "ar" ? "فتح القائمة" : "Open navigation" }).click();
        await expect(page.getByRole("navigation", { name: language === "ar" ? "قائمة التنقل" : "Mobile navigation" })).toBeVisible();
        await expect(page.getByRole("group", { name: language === "ar" ? "اللغة" : "Language" })).toBeVisible();
      }
      expect(consoleErrors).toEqual([]);
    });
  }
}
