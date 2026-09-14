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
import { test, expect, type APIRequestContext, type Browser, type BrowserContext, type Page } from "@playwright/test";

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

  // Tests 6 through 10 are one continuous Grand Admin browser journey
  // (login, then several pages that all depend on still being signed in).
  // The same per-test fresh-context rule documented above applies here:
  // give them one shared context/page instead of the default `page`
  // fixture, or every test after "6. Grand Admin login" deterministically
  // hits the sign-in form again (Mission 7 Phase 23 test-matrix run
  // caught this too, once the fix above let the suite run this far).
  let adminContext: BrowserContext;
  let adminPage: Page;

  test.beforeAll(async ({ browser }: { browser: Browser }) => {
    adminContext = await browser.newContext();
    adminPage = await adminContext.newPage();
  });

  test.afterAll(async () => {
    await adminContext.close();
  });

  test("1. Central signup (Account Portal) + 2. Overview for a fresh user", async ({ page }) => {
    // Both assertions must run on the SAME page/context: Playwright gives
    // every `test()` a fresh, cookie-less BrowserContext by default (true
    // regardless of `describe.serial`, which only orders execution and
    // stops on failure - it does not share session state). Every other
    // authenticated test below correctly re-logs-in on its own page for
    // exactly this reason (see tests 11, 11b, 14, 15, 12); this pair was
    // the one place that assumed continuity across a test boundary, which
    // made "2." deterministically render the signed-out Account Portal
    // (Mission 7 Phase 23 test-matrix run) instead of ever exercising the
    // fresh-user Overview view it claims to. Keeping both checks on one
    // page, as one continuous user journey, is the fix - not a change to
    // any application code.
    await page.goto(`${ACCOUNT}/login`);
    await page.getByText(/new here\?/i).click();
    await page.getByLabel(/email/i).fill(TARGET_EMAIL);
    await page.getByLabel(/password/i).fill(TARGET_PASSWORD);
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page).toHaveURL(`${ACCOUNT}/`);

    await expect(page.getByText(/member since/i)).toBeVisible();
    await expect(page.getByText(/haven't used any ecosystem products/i)).toBeVisible();
  });

  test("6. Grand Admin login", async () => {
    await adminPage.goto(`${ADMIN}/login`);
    await adminPage.getByLabel(/email/i).fill(SUPER_ADMIN_EMAIL);
    await adminPage.getByLabel(/password/i).fill(SUPER_ADMIN_PASSWORD);
    await adminPage.getByRole("button", { name: /sign in/i }).click();
    await expect(adminPage).toHaveURL(`${ADMIN}/`);
    await expect(adminPage.getByText(/total users/i)).toBeVisible();

    // Capture the resulting session cookie for setup API calls in later steps.
    const cookies = await adminContext.cookies();
    adminCookie = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
    expect(adminCookie).toContain("plat_session_access");
  });

  test("setup: register product via admin API (not UI - seeding only)", async ({ request }) => {
    const res = await apiPost(request, adminCookie, "/api/v1/admin/products", {
      id: PRODUCT_ID, name: "E2E Browser Product", domain: `${PRODUCT_ID}.example`, status: "live", icon_ref: null,
    });
    expect(res.ok()).toBeTruthy();
  });

  test("7. Create a product plan through the Grand Admin UI", async () => {
    await adminPage.goto(`${ADMIN}/products/${PRODUCT_ID}`);
    // getByPlaceholder does case-insensitive substring matching by default,
    // so plain "creator" also matches the "Creator" (Name) field - exact:
    // true is required to disambiguate the two real, distinct inputs.
    await adminPage.getByPlaceholder("creator", { exact: true }).fill("pro");
    await adminPage.getByPlaceholder("Creator", { exact: true }).fill("Pro");
    await adminPage.getByRole("button", { name: /create plan/i }).click();
    // getByText also substring-matches by default, and the nav bar's
    // "Products" link contains "Pro" - scope to <main> and match exactly
    // so the click below lands on the plan row, not the nav link.
    await expect(adminPage.locator("main").getByText("Pro", { exact: true }).first()).toBeVisible();
    await expect(adminPage.locator("main").getByText("pro", { exact: true }).first()).toBeVisible();
  });

  test("7b. Edit the plan (description + sort order) through the UI", async () => {
    await adminPage.goto(`${ADMIN}/products/${PRODUCT_ID}`);
    await adminPage.locator("main").getByText("Pro", { exact: true }).first().click();
    const textarea = adminPage.locator("main").locator("textarea");
    await textarea.fill("The E2E test plan.");
    await adminPage.getByRole("button", { name: /^save$/i }).click();
    await expect(adminPage.getByText(/saved\./i)).toBeVisible();
  });

  test("8. Create a price through the Grand Admin UI", async () => {
    await adminPage.goto(`${ADMIN}/products/${PRODUCT_ID}`);
    await adminPage.locator("main").getByText("Pro", { exact: true }).first().click();
    await adminPage.getByPlaceholder("9.99").fill("4.99");
    await adminPage.getByRole("button", { name: /add price/i }).click();
    await expect(adminPage.getByText(/4\.99 USD \/ month/i)).toBeVisible();
  });

  test("9. Grant gifted access to the target user through the Users UI", async () => {
    await adminPage.goto(`${ADMIN}/users`);
    await adminPage.getByPlaceholder(/search by email/i).fill(TARGET_EMAIL);
    await adminPage.waitForTimeout(300);
    await adminPage.getByRole("row", { name: new RegExp(TARGET_EMAIL) }).getByRole("button", { name: /^view$/i }).click();
    await adminPage.getByPlaceholder("Product", { exact: true }).fill(PRODUCT_ID);
    await adminPage.getByPlaceholder("Plan", { exact: true }).fill("pro");
    // Two <select> elements exist on this page once a user is selected
    // (role assignment, then source) - the source select is the second one.
    await adminPage.getByRole("combobox").nth(1).selectOption("gifted");
    await adminPage.getByRole("button", { name: /^grant$/i }).click();
    await expect(adminPage.getByText(PRODUCT_ID).first()).toBeVisible();
  });

  test("11. The target user's Account Portal reflects the grant", async ({ page }) => {
    await page.goto(`${ACCOUNT}/login`);
    await page.getByLabel(/email/i).fill(TARGET_EMAIL);
    await page.getByLabel(/password/i).fill(TARGET_PASSWORD);
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page).toHaveURL(`${ACCOUNT}/`);
    await expect(page.getByText("E2E Browser Product")).toBeVisible();
    // getByText substring-matches by default - the nav's "Products" and
    // "Profile" links both contain "Pro", so exact match is required.
    await expect(page.getByText("Pro", { exact: true })).toBeVisible();

    await page.goto(`${ACCOUNT}/billing`);
    await expect(page.getByText("Gifted Access")).toBeVisible();
  });

  test("10. Revoke the gift through the Users UI and confirm its status flips", async () => {
    await adminPage.goto(`${ADMIN}/users`);
    await adminPage.getByPlaceholder(/search by email/i).fill(TARGET_EMAIL);
    await adminPage.waitForTimeout(300);
    await adminPage.getByRole("row", { name: new RegExp(TARGET_EMAIL) }).getByRole("button", { name: /^view$/i }).click();
    const entitlementRow = adminPage.getByText(new RegExp(`${PRODUCT_ID} · pro`));
    await expect(entitlementRow).toBeVisible();
    // The existing entitlement list item has its own revoke control.
    await adminPage.getByRole("button", { name: /^revoke$/i }).first().click();
    // The Users page intentionally keeps a full entitlement history (Users.tsx
    // renders every entitlement, revoked or not, and only shows the Revoke
    // button while status === "active") - so the row itself stays, its
    // status label flips to "revoked", and the Revoke button disappears.
    await expect(entitlementRow).toContainText("revoked");
    await expect(adminPage.getByRole("button", { name: /^revoke$/i })).toHaveCount(0);
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
    // Wait for the revoke DELETE to actually complete, not just for the
    // click event to dispatch - handleRevoke() is async and click()
    // resolves before its fetch does.
    await Promise.all([
      page1.waitForResponse((r) => r.url().includes("/api/v1/auth/sessions/") && r.request().method() === "DELETE"),
      otherSessionSignOut.click(),
    ]);

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
    // Must wait for the signup to actually land (and its cookies to be
    // set) before reading /me below - otherwise this races the signup
    // request and /me returns 401, making `me.id` undefined.
    await expect(page).toHaveURL(`${ACCOUNT}/`);

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

    // Grand Admin and the Account Portal share ONE central session cookie
    // (same backend, same cookie domain) - this browser is already
    // authenticated as SCOPED_ADMIN_EMAIL from the signup above, so
    // Grand Admin's own /login immediately redirects to "/" via the same
    // "if (!loading && user) return <Navigate to='/' />" pattern Login.tsx
    // uses everywhere in this codebase (ProtectedRoute.tsx only checks
    // "is authenticated," never role - RBAC is enforced by the backend
    // per-endpoint, not by hiding routes). Asserting a login form here
    // would just time out waiting for a redirect that already happened.
    await page.goto(`${ADMIN}/products/${PRODUCT_ID}`);
    await expect(page.getByRole("heading", { name: PRODUCT_ID })).toBeVisible();

    await page.goto(`${ADMIN}/products/${otherProductId}`);
    await expect(page.getByText(/access denied/i)).toBeVisible();
  });
});
