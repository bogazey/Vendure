import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Billing from "./Billing";
import { useAuth } from "../context/AuthContext";
import i18n from "../i18n";
import type { AccountOut } from "../types/commercial";

vi.mock("../context/AuthContext", () => ({ useAuth: vi.fn() }));
vi.mock("../services/api", () => ({
  api: { manageSubscription: vi.fn(), updatePaymentMethod: vi.fn(), paymentHistory: vi.fn(), invoice: vi.fn() },
}));

function makeAccount(overrides: Partial<AccountOut["subscription"]> = {}): AccountOut {
  return {
    user: { id: "u1", email: "a@example.com", email_verified: true, role: "user", status: "active", created_at: "2026-01-01T00:00:00Z" },
    subscription: {
      plan: "creator", status: "active", billing_period: null,
      current_period_start: null, current_period_end: null, cancel_at_period_end: false,
      provider: "paddle", ...overrides,
    },
    usage: { plan: "creator", period_start: "2026-01-01T00:00:00Z", period_end: "2026-02-01T00:00:00Z", credits_included: 500, credits_used: 10, credits_remaining: 490, daily_free_downloads_used: null, daily_free_downloads_remaining: null },
    features: { plan: "creator", max_resolution_height: null, can_use_4k: true, can_use_batch: true, can_use_advanced_formats: true, can_use_clip_range: true, can_use_browser_cookies: true, can_use_original_container: true, can_use_creator_tools: true, ads_enabled: false, queue_priority: 10, monthly_credits: 500, daily_free_downloads: null },
  };
}

function mockAccount(account: AccountOut) {
  vi.mocked(useAuth).mockReturnValue({ account, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
}

describe("Billing page - gifted subscription awareness", () => {
  it("shows a paid user the normal Manage billing entry point and Paddle controls", () => {
    mockAccount(makeAccount({ provider: "paddle", status: "active", billing_period: "monthly" }));
    render(<MemoryRouter><Billing /></MemoryRouter>);

    expect(screen.getByRole("link", { name: "Manage billing" })).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Gifted Subscription")).not.toBeInTheDocument();
  });

  it("shows a gifted user the Gifted Subscription badge/notice and no Paddle-managed actions", () => {
    mockAccount(makeAccount({ provider: "gifted", status: "active" }));
    render(<MemoryRouter><Billing /></MemoryRouter>);

    expect(screen.getAllByText("Gifted Subscription").length).toBeGreaterThan(0);
    expect(screen.getByText("This subscription was provided by Loady and does not require payment.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Manage billing" })).not.toBeInTheDocument();
    // No Paddle-only actions must ever be reachable for a gifted subscription.
    expect(screen.queryByRole("button", { name: "Update payment method" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel at period end" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change plan" })).not.toBeInTheDocument();
  });

  it("still shows a Free user the normal upgrade prompt", () => {
    mockAccount(makeAccount({ plan: "free" as never, provider: "none", status: "none" as never }));
    render(<MemoryRouter><Billing /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Upgrade plan" })).toBeInTheDocument();
  });

  it("renders the gifted notice in Arabic", async () => {
    await i18n.changeLanguage("ar");
    mockAccount(makeAccount({ provider: "gifted", status: "active" }));
    render(<MemoryRouter><Billing /></MemoryRouter>);
    expect(screen.getAllByText("اشتراك مُهدى").length).toBeGreaterThan(0);
    expect(screen.getByText("تم توفير هذا الاشتراك من Loady ولا يتطلب أي دفعة.")).toBeInTheDocument();
    await i18n.changeLanguage("en");
  });
});
