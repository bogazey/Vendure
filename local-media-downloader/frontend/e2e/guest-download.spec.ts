import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const ANALYZE_RESPONSE = {
  url: "https://www.youtube.com/watch?v=abc123",
  platform: "youtube",
  media_type: "video",
  id: "abc123",
  title: "A Test Video",
  uploader: "someone",
  thumbnail: null,
  duration: 120,
  description: null,
  image_url: null,
  image_width: null,
  image_height: null,
  image_ext: null,
  is_playlist: false,
  playlist_title: null,
  playlist_count: null,
  playlist_entries_preview: [],
  media_items: [],
  video_presets: [{ key: "360", label: "360p", kind: "video", available: true, height: 360, expected_container: "mp4", will_transcode: false }],
  audio_presets: [{ key: "best", label: "Best", kind: "audio", available: true, height: null, expected_container: "m4a", will_transcode: false }],
  advanced_formats: [],
};

const DOWNLOAD_JOB = {
  id: "job-1",
  url: ANALYZE_RESPONSE.url,
  platform: "youtube",
  title: ANALYZE_RESPONSE.title,
  uploader: ANALYZE_RESPONSE.uploader,
  thumbnail: null,
  media_type: "video",
  stage: "queued",
  progress_percent: 0,
  speed_bps: null,
  downloaded_bytes: null,
  total_bytes: null,
  eta_seconds: null,
  filepath: null,
  error_message: null,
  created_at: "2026-01-01T00:00:00Z",
  completed_at: null,
};

/** Mocks a fully anonymous visitor: /api/account 401s (no session cookie
 * at all), and the guest-specific endpoints answer with a configurable
 * remaining count - no real backend needed, matching e2e/admin.spec.ts's
 * approach. */
async function mockGuestApi(page: Page, remaining: number) {
  await page.route("http://127.0.0.1:8000/api/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const method = route.request().method();
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (pathname.endsWith("/api/account")) return json({ message: "Sign in to continue.", code: "AUTH_REQUIRED" }, 401);
    if (pathname.endsWith("/api/settings")) return json({ theme: "system" });
    if (pathname.endsWith("/api/health")) {
      return json({ status: "ok", ytdlp_version: "2026.01.01", ffmpeg_available: true, ffmpeg_path: "/usr/bin/ffmpeg", download_dir: "/data/downloads", download_dir_writable: true, database_ok: true });
    }
    if (pathname.endsWith("/api/ads/placements")) return json([]);
    if (pathname.endsWith("/api/downloads/guest-quota")) return json({ remaining, limit: 2 });
    if (pathname.endsWith("/api/downloads") && method === "GET") return json([]);
    if (pathname.endsWith("/api/analyze")) return json(ANALYZE_RESPONSE);
    if (pathname.endsWith("/api/downloads") && method === "POST") {
      if (remaining <= 0) {
        return json({ message: "You've used your free downloads. Create a free account to keep downloading.", code: "GUEST_QUOTA_EXCEEDED" }, 402);
      }
      return json(DOWNLOAD_JOB, 201);
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

test("a signed-out visitor can analyze and download without being redirected to signup", async ({ page }) => {
  await mockGuestApi(page, 2);
  await page.goto("/");

  await page.getByPlaceholder(/paste a/i).first().fill("https://www.youtube.com/watch?v=abc123");
  await page.getByRole("button", { name: "Continue" }).click();

  // The bug this fixes: clicking through must land on the downloader, not
  // be bounced to /signup just for trying the product.
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText("2 free downloads — no account required")).toBeVisible();
  await expect(page.getByText("A Test Video")).toBeVisible();

  await page.getByRole("button", { name: "Start Download" }).click();
  await expect(page.getByText("Added to the download queue below.")).toBeVisible();
  await expect(page).toHaveURL(/\/dashboard$/); // still no redirect after a successful download
});

test("shows one-remaining after the first guest download and a signup CTA once exhausted", async ({ page }) => {
  await mockGuestApi(page, 1);
  await page.goto("/dashboard");

  await expect(page.getByText("1 free download remaining")).toBeVisible();

  await page.getByPlaceholder(/paste a/i).fill("https://www.youtube.com/watch?v=abc123");
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page.getByRole("button", { name: "Start Download" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Create free account" })).not.toBeVisible();
});

test("a guest with no downloads left sees a clear signup CTA instead of the format selector", async ({ page }) => {
  await mockGuestApi(page, 0);
  await page.goto("/dashboard");

  await expect(page.getByText("You've used your free downloads")).toBeVisible();

  await page.getByPlaceholder(/paste a/i).fill("https://www.youtube.com/watch?v=abc123");
  await page.getByRole("button", { name: "Analyze" }).click();

  const cta = page.getByRole("link", { name: "Create free account" });
  await expect(cta).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Download" })).not.toBeVisible();

  await cta.click();
  await expect(page).toHaveURL(/\/signup$/);
});

test("Arabic guest banner renders translated and RTL", async ({ page }) => {
  await mockGuestApi(page, 2);
  await page.addInitScript(() => localStorage.setItem("loady-language", "ar"));
  await page.goto("/dashboard");

  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByText("تنزيلان مجانيان — بلا حاجة لحساب")).toBeVisible();
});
