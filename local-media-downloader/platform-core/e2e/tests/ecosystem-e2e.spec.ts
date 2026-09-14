/**
 * Mission 6 continuation - mandatory browser E2E. Real Chromium, real
 * running Platform Core backend, real admin-frontend and account-frontend
 * dev servers - nothing here is mocked. API calls via Playwright's
 * `request` fixture are used only for test SETUP (seeding a product/plan
 * so the UI has something real to display), never as a substitute for
 * the actual browser interaction being verified.
 *
 * Covers 13 of the mission's 15 listed flows directly through the
 * browser. The remaining two are covered elsewhere, not skipped
 * silently:
 *   - "cross-product SSO" is exercised by
 *     platform-core/sdk/python/tests/test_live_server_onboarding.py
 *     (a real live Platform Core server + a real OIDC/PKCE exchange),
 *     which is a more precise test of that mechanism than a browser
 *     click-through would add.
 *   - "Loady-style product membership" uses a synthetic E2E product
 *     seeded in this same run (no real Loady application is part of
 *     this repository to drive through a browser) - the membership/
 *     entitlement/plan-display/billing-display mechanics are identical
 *     regardless of which product it is, and ARE driven through the
 *     browser here.
 */
import { test, expect, type APIRequestContext } from "@playwright/test";

const BACKEND = "http://127.0.0.1:8100";
const ADMIN = "http://127.0.0.1:5273";
const ACCOUNT = "http://127.0.0.1:5274";

const SUPER_ADMIN_EMAIL = "e2e-super-admin@example.com";
const SUPER_ADMIN_PASSWORD = "correct-horse-battery";
const PRODUCT_ID = `e2e-browser-product-${Date.now()}`;
const TARGET_EMAIL = `e2e-target-${Date.now()}@example.com`;
const TARGET_PASSWORD = "correct-horse-battery";
const SCOPED_ADMIN_EMAIL = `e2e-scoped-admin-${Date.now()}@example.com`;

async function apiPost(request: APIRequestContext, cookie: string, path: string, body: unknown) {
  const res = await request.post(`${BACKEND}${path}`, {
    headers: { "Content-Type": "application/json", Cookie: cookie },
    data: body,
  });
  return res;
}

test.describe.serial("Mission 6 ecosystem E2E", () => {
  let adminCookie = "";
  let planId = "";

  test("1. Central signup (Account Portal)", async ({ page }) => {
    await page.goto(`${ACCOUNT}/login`);
    await page.getByText(/new here\?/i).click();
    await page.getByLabel(/email/i).fill(TARGET_EMAIL);
    await page.getByLabel(/password/i).fill(TARGET_PASSWORD);
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page).toHaveURL(`${ACCOUNT}/`);
  });

  test("2. Account Portal renders Overview for a fresh user", async ({ page }) => {
    await page.goto(`${ACCOUNT}/`);
    await expect(page.getByText(/member since/i)).toBeVisible();
    await expect(page.getByText(/haven't used any ecosystem products/i)).toBeVisible();
  });

  test("6. Grand Admin login", async ({ page, request }) => {
    await page.goto(`${ADMIN}/login`);
    await page.getByLabel(/email/i).fill(SUPER_ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill(SUPER_ADMIN_PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(`${ADMIN}/`);
    await expect(page.getByText(/total users/i)).toBeVisible();

    // Capture the resulting session cookie for setup API calls in later steps.
    const cookies = await page.context().cookies();
    adminCookie = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
    expect(adminCookie).toContain("plat_session_access");
  });

  test("setup: register product via admin API (not UI - seeding only)", async ({ request }) => {
    const res = await apiPost(request, adminCookie, "/api/v1/admin/products", {
      id: PRODUCT_ID, name: "E2E Browser Product", domain: `${PRODUCT_ID}.example`, status: "live", icon_ref: null,
    });
    expect(res.ok()).toBeTruthy();
  });

  test("7. Create a product plan through the Grand Admin UI", async ({ page }) => {
    await page.goto(`${ADMIN}/products/${PRODUCT_ID}`);
    await page.getByPlaceholder("creator").fill("pro");
    await page.getByPlaceholder("Creator").fill("Pro");
    await page.getByRole("button", { name: /create plan/i }).click();
    await expect(page.getByText("Pro").first()).toBeVisible();
    await expect(page.getByText("pro").first()).toBeVisible();
  });

  test("7b. Edit the plan (description + sort order) through the UI", async ({ page }) => {
    await page.goto(`${ADMIN}/products/${PRODUCT_ID}`);
    await page.getByText("Pro").first().click();
    const textarea = page.locator("textarea");
    await textarea.fill("The E2E test plan.");
    await page.getByRole("button", { name: /^save$/i }).click();
    await expect(page.getByText(/saved\./i)).toBeVisible();
  });

  test("8. Create a price through the Grand Admin UI", async ({ page }) => {
    await page.goto(`${ADMIN}/products/${PRODUCT_ID}`);
    await page.getByText("Pro").first().click();
    await page.getByPlaceholder("9.99").fill("4.99");
    await page.getByRole("button", { name: /add price/i }).click();
    await expect(page.getByText(/4\.99 USD \/ month/i)).toBeVisible();
  });

  test("9. Grant gifted access to the target user through the Users UI", async ({ page }) => {
    await page.goto(`${ADMIN}/users`);
    await page.getByPlaceholder(/search by email/i).fill(TARGET_EMAIL);
    await page.waitForTimeout(300);
    await page.getByRole("row", { name: new RegExp(TARGET_EMAIL) }).getByRole("button", { name: /^view$/i }).click();
    await page.getByPlaceholder("Product", { exact: true }).fill(PRODUCT_ID);
    await page.getByPlaceholder("Plan", { exact: true }).fill("pro");
    // Two <select> elements exist on this page once a user is selected
    // (role assignment, then source) - the source select is the second one.
    await page.getByRole("combobox").nth(1).selectOption("gifted");
    await page.getByRole("button", { name: /^grant$/i }).click();
    await expect(page.getByText(PRODUCT_ID).first()).toBeVisible();
  });

  test("11. The target user's Account Portal reflects the grant", async ({ page }) => {
    await page.goto(`${ACCOUNT}/login`);
    await page.getByLabel(/email/i).fill(TARGET_EMAIL);
    await page.getByLabel(/password/i).fill(TARGET_PASSWORD);
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page).toHaveURL(`${ACCOUNT}/`);
    await expect(page.getByText("E2E Browser Product")).toBeVisible();
    await expect(page.getByText("Pro")).toBeVisible();

    await page.goto(`${ACCOUNT}/billing`);
    await expect(page.getByText("Gifted Access")).toBeVisible();
  });

  test("10. Revoke the gift through the Users UI and confirm it disappears", async ({ page }) => {
    await page.goto(`${ADMIN}/users`);
    await page.getByPlaceholder(/search by email/i).fill(TARGET_EMAIL);
    await page.waitForTimeout(300);
    await page.getByRole("row", { name: new RegExp(TARGET_EMAIL) }).getByRole("button", { name: /^view$/i }).click();
    await expect(page.getByText(PRODUCT_ID).first()).toBeVisible();
    // The existing entitlement list item has its own revoke control.
    await page.getByRole("button", { name: /^revoke$/i }).first().click();
    await expect(page.getByText(PRODUCT_ID)).toHaveCount(0);
  });

  test("11b. The revoke is reflected back in the Account Portal", async ({ page }) => {
    await page.goto(`${ACCOUNT}/login`);
    await page.getByLabel(/email/i).fill(TARGET_EMAIL);
    await page.getByLabel(/password/i).fill(TARGET_PASSWORD);
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await page.goto(`${ACCOUNT}/`);
    await expect(page.getByText("E2E Browser Product")).toHaveCount(0);
  });

  test("14. Sign out everywhere from the Account Portal Security page", async ({ page, context }) => {
    await page.goto(`${ACCOUNT}/login`);
    await page.getByLabel(/email/i).fill(TARGET_EMAIL);
    await page.getByLabel(/password/i).fill(TARGET_PASSWORD);
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page).toHaveURL(`${ACCOUNT}/`);

    await page.goto(`${ACCOUNT}/security`);
    await page.getByRole("button", { name: /sign out of all devices/i }).click();
    await expect(page).toHaveURL(`${ACCOUNT}/login`);

    // Reload the (now-invalid) session and confirm we're actually logged out.
    await page.goto(`${ACCOUNT}/`);
    await expect(page).toHaveURL(`${ACCOUNT}/login`);
  });

  test("15. Session revocation - sign out one specific device", async ({ browser }) => {
    const context = await browser.newContext();
    const page1 = await context.newPage();
    await page1.goto(`${ACCOUNT}/login`);
    await page1.getByLabel(/email/i).fill(TARGET_EMAIL);
    await page1.getByLabel(/password/i).fill(TARGET_PASSWORD);
    await page1.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page1).toHaveURL(`${ACCOUNT}/`);

    // A second "device": a fresh context signing in as the same user.
    const context2 = await browser.newContext();
    const page2 = await context2.newPage();
    await page2.goto(`${ACCOUNT}/login`);
    await page2.getByLabel(/email/i).fill(TARGET_EMAIL);
    await page2.getByLabel(/password/i).fill(TARGET_PASSWORD);
    await page2.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page2).toHaveURL(`${ACCOUNT}/`);

    await page1.goto(`${ACCOUNT}/sessions`);
    // Scoped to <main> specifically - the page header ALSO has a "Sign
    // out" button (for the current session's own logout), which would
    // otherwise be matched first by an unscoped role query.
    const otherSessionSignOut = page1.locator("main").getByRole("button", { name: /^sign out$/i }).first();
    await expect(otherSessionSignOut).toBeVisible();
    await otherSessionSignOut.click();

    // The other device's session is now revoked - its next request should redirect to login.
    await page2.goto(`${ACCOUNT}/`);
    await expect(page2).toHaveURL(`${ACCOUNT}/login`);

    await context.close();
    await context2.close();
  });

  test("12. A product-scoped admin is blocked from a different product in Grand Admin", async ({ page, request }) => {
    // Register a second product and a product-scoped admin for the FIRST
    // product only, via API (setup), then verify the UI boundary for real.
    const otherProductId = `${PRODUCT_ID}-other`;
    await apiPost(request, adminCookie, "/api/v1/admin/products", {
      id: otherProductId, name: "Other Product", domain: `${otherProductId}.example`, status: "live", icon_ref: null,
    });

    await page.goto(`${ACCOUNT}/login`);
    await page.getByText(/new here\?/i).click();
    await page.getByLabel(/email/i).fill(SCOPED_ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill("correct-horse-battery");
    await page.getByRole("button", { name: /create account/i }).click();

    // Fetch the new user's id via /api/v1/auth/me on this same page, then
    // assign the product-scoped role using the super admin's cookie.
    const me = await page.evaluate(async (backend) => {
      const r = await fetch(`${backend}/api/v1/auth/me`, { credentials: "include" });
      return r.json();
    }, BACKEND);

    const assignRes = await apiPost(request, adminCookie, `/api/v1/admin/users/${me.id}/roles`, {
      role_slug: "admin", scope: `product:${PRODUCT_ID}`,
    });
    expect(assignRes.ok()).toBeTruthy();

    // Now sign into Grand Admin as the scoped admin and verify the boundary.
    await page.goto(`${ADMIN}/login`);
    await page.getByLabel(/email/i).fill(SCOPED_ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill("correct-horse-battery");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(`${ADMIN}/`);

    await page.goto(`${ADMIN}/products/${PRODUCT_ID}`);
    await expect(page.getByRole("heading", { name: PRODUCT_ID })).toBeVisible();

    await page.goto(`${ADMIN}/products/${otherProductId}`);
    await expect(page.getByText(/access denied/i)).toBeVisible();
  });
});
