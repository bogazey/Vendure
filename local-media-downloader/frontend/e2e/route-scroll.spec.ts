import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const bodyScrollTop = (page: Page) =>
  page.evaluate(() => document.body.scrollTop);

test("restores route scroll while preserving marketing hash navigation", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => {
    document.documentElement.style.overflowY = "hidden";
    document.body.style.height = "100vh";
    document.body.style.overflowY = "auto";
  });
  await page.evaluate(() => document.body.scrollTo({ top: 1_200 }));
  await expect.poll(() => bodyScrollTop(page)).toBeGreaterThan(0);

  await page.locator('.premium-nav a[href="/pricing"]').click();
  await expect(page).toHaveURL(/\/pricing$/);
  await expect.poll(() => bodyScrollTop(page)).toBe(0);

  await page.locator('.premium-nav a[href="/#features"]').click();
  await expect(page).toHaveURL(/\/#features$/);
  await expect.poll(() => page.locator("#features").evaluate((element) =>
    Math.round(element.getBoundingClientRect().top),
  )).toBe(96);

  await page.locator('.premium-nav a[href="/pricing"]').click();
  await expect.poll(() => bodyScrollTop(page)).toBe(0);

  await page.locator('.premium-nav a[href="/#how-it-works"]').click();
  await expect(page).toHaveURL(/\/#how-it-works$/);
  await expect.poll(() => page.locator("#how-it-works").evaluate((element) =>
    Math.round(element.getBoundingClientRect().top),
  )).toBe(96);
});
