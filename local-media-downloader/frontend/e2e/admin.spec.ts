import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const ADMIN_ACCOUNT = {
  user: { id: "admin-1", email: "admin@example.com", email_verified: true, role: "admin", status: "active", created_at: "2026-01-01T00:00:00Z" },
  subscription: { plan: "pro", status: "active", billing_period: "monthly", current_period_start: null, current_period_end: null, cancel_at_period_end: false },
  usage: { plan: "pro", period_start: "2026-01-01T00:00:00Z", period_end: "2026-02-01T00:00:00Z", credits_included: 150, credits_used: 10, credits_remaining: 140, daily_free_downloads_used: null, daily_free_downloads_remaining: null },
  features: { plan: "pro", max_resolution_height: 1080, can_use_4k: false, can_use_batch: true, can_use_advanced_formats: true, can_use_clip_range: true, can_use_browser_cookies: true, can_use_original_container: true, can_use_creator_tools: false, ads_enabled: false, queue_priority: 1, monthly_credits: 150, daily_free_downloads: null },
};

const OVERVIEW = {
  total_users: 42,
  active_users: 40,
  disabled_users: 2,
  paid_subscribers: 12,
  free_count: 30,
  pro_count: 9,
  creator_count: 3,
  credits_consumed_current_period: 517,
  recent_billing_failures: [],
  recent_admin_actions: [],
};

const USERS = {
  users: [
    { id: "user-1", email: "target@example.com", status: "active", role: "user", plan: "pro", subscription_status: "active", credits_used: 10, credits_included: 150, credits_bonus: 0, created_at: "2026-01-01T00:00:00Z" },
  ],
  total: 42,
};

async function mockAdminApi(page: Page) {
  await page.route("http://127.0.0.1:8000/api/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

    if (pathname.endsWith("/api/account")) return json(ADMIN_ACCOUNT);
    if (pathname.endsWith("/api/settings")) return json({ theme: "system" });
    if (pathname.endsWith("/api/health")) {
      return json({ status: "ok", ytdlp_version: "2026.01.01", ffmpeg_available: true, ffmpeg_path: "/usr/bin/ffmpeg", download_dir: "/data/downloads", download_dir_writable: true, database_ok: true });
    }
    if (pathname.endsWith("/api/admin/overview")) return json(OVERVIEW);
    if (pathname.endsWith("/api/admin/users")) return json(USERS);
    if (pathname.endsWith("/api/admin/billing-events")) return json([]);
    if (pathname.endsWith("/api/admin/audit-log")) return json([]);
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

test("admin overview loads for an authenticated admin", async ({ page }) => {
  await mockAdminApi(page);
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Admin" })).toBeVisible();
  await expect(page.getByText("Total users")).toBeVisible();
  await expect(page.getByText("42")).toBeVisible();
});

test("admin sections navigate via the tab strip", async ({ page }) => {
  await mockAdminApi(page);
  await page.goto("/admin");
  await expect(page.getByText("Total users")).toBeVisible();

  await page.getByRole("navigation", { name: "Admin sections" }).getByRole("link", { name: "Users" }).click();
  await expect(page).toHaveURL(/\/admin\/users$/);
  await expect(page.getByText("target@example.com")).toBeVisible();

  await page.getByRole("navigation", { name: "Admin sections" }).getByRole("link", { name: "Billing" }).click();
  await expect(page).toHaveURL(/\/admin\/billing$/);
  await expect(page.getByText("No billing events yet.")).toBeVisible();

  await page.getByRole("navigation", { name: "Admin sections" }).getByRole("link", { name: "Activity" }).click();
  await expect(page).toHaveURL(/\/admin\/activity$/);
  await expect(page.getByText("No admin actions recorded yet.")).toBeVisible();

  await page.getByRole("navigation", { name: "Admin sections" }).getByRole("link", { name: "System" }).click();
  await expect(page).toHaveURL(/\/admin\/system$/);
  await expect(page.getByText("FFmpeg", { exact: true })).toBeVisible();
});

const ADMIN_PAGES = ["/admin", "/admin/users", "/admin/billing", "/admin/activity", "/admin/system"];

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
]) {
  for (const language of ["en", "ar"] as const) {
    test(`${language} admin has no horizontal overflow at ${viewport.width}px`, async ({ page }) => {
      await mockAdminApi(page);
      await page.setViewportSize(viewport);
      await page.addInitScript((lang) => localStorage.setItem("loady-language", lang), language);

      for (const path of ADMIN_PAGES) {
        await page.goto(path);
        await expect(page.locator("html")).toHaveAttribute("dir", language === "ar" ? "rtl" : "ltr");
        await expect(page.getByRole("heading", { name: language === "ar" ? "الإدارة" : "Admin", exact: true })).toBeVisible();
        const overflow = await page.evaluate(() => ({
          body: document.body.scrollWidth - document.body.clientWidth,
          root: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        }));
        expect(overflow.body, `${language} body overflow on ${path} at ${viewport.width}px`).toBeLessThanOrEqual(0);
        expect(overflow.root, `${language} root overflow on ${path} at ${viewport.width}px`).toBeLessThanOrEqual(0);
      }
    });
  }
}
