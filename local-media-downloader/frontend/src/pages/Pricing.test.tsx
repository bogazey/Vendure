import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Pricing from "./Pricing";
import { api } from "../services/api";
import { useAuth } from "../context/AuthContext";
import i18n from "../i18n";
import type { AccountOut, Plan, SubscriptionStatus } from "../types/commercial";

vi.mock("../context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("../services/api", () => ({
  api: { createCheckout: vi.fn() },
  ApiError: class ApiError extends Error {},
}));

function buildAccount(plan: Plan, status: SubscriptionStatus = "active"): AccountOut {
  return {
    user: { id: "u1", email: "a@example.com", email_verified: true, role: "user", status: "active", created_at: "2026-01-01T00:00:00Z" },
    subscription: { plan, status, billing_period: plan === "free" ? null : "monthly", current_period_start: null, current_period_end: null, cancel_at_period_end: false, provider: plan === "free" ? "none" : "paddle" },
    usage: { plan, period_start: "2026-01-01T00:00:00Z", period_end: "2026-02-01T00:00:00Z", credits_included: null, credits_used: 0, credits_remaining: null, daily_free_downloads_used: null, daily_free_downloads_remaining: null },
    features: { plan, max_resolution_height: null, can_use_4k: true, can_use_batch: true, can_use_advanced_formats: true, can_use_clip_range: true, can_use_browser_cookies: true, can_use_original_container: true, can_use_creator_tools: false, ads_enabled: false, queue_priority: 5, monthly_credits: null, daily_free_downloads: null },
  };
}

function mockAccount(account: AccountOut | null) {
  vi.mocked(useAuth).mockReturnValue({ account, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
}

function renderPricing() {
  return render(
    <MemoryRouter>
      <Pricing />
    </MemoryRouter>
  );
}

function cardButton(name: RegExp | string) {
  return screen.getByRole("button", { name });
}

describe("Pricing", () => {
  it("shows monthly prices by default and switches to annual on toggle", async () => {
    mockAccount(null);
    renderPricing();

    expect(screen.getByText("$4.99")).toBeInTheDocument();
    expect(screen.getByText("$9.99")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Annual/ }));

    expect(screen.getByText("$47.90")).toBeInTheDocument();
    expect(screen.getByText("$95.90")).toBeInTheDocument();
  });

  describe("plan-aware CTAs", () => {
    it("Free user: Free = Current plan, Pro = Upgrade, Creator = Upgrade", () => {
      mockAccount(buildAccount("free", "none"));
      renderPricing();

      const current = screen.getAllByText("Current plan");
      expect(current).toHaveLength(1);
      expect(current[0].closest("button")).toBeDisabled();

      const upgrades = screen.getAllByRole("button", { name: "Upgrade" });
      expect(upgrades).toHaveLength(2);
      upgrades.forEach((btn) => expect(btn).not.toBeDisabled());
      expect(screen.queryByText("Manage subscription")).not.toBeInTheDocument();
    });

    it("Pro user: Pro = Current plan, Creator = Upgrade, Free is not Upgrade", () => {
      mockAccount(buildAccount("pro"));
      renderPricing();

      const current = screen.getAllByText("Current plan");
      expect(current).toHaveLength(1);
      expect(current[0].closest("button")).toBeDisabled();

      expect(screen.getAllByRole("button", { name: "Upgrade" })).toHaveLength(1);
      expect(screen.getByRole("button", { name: "Manage subscription" })).toBeInTheDocument();
    });

    it("Creator user: Creator = Current plan, Pro is NOT Upgrade, Free is NOT Upgrade", () => {
      mockAccount(buildAccount("creator"));
      renderPricing();

      const current = screen.getAllByText("Current plan");
      expect(current).toHaveLength(1);
      expect(current[0].closest("button")).toBeDisabled();

      // No card should ever show "Upgrade" once the account is already on the highest tier.
      expect(screen.queryByRole("button", { name: "Upgrade" })).not.toBeInTheDocument();
      expect(screen.getAllByRole("button", { name: "Manage subscription" })).toHaveLength(2);
    });
  });

  describe("Manage subscription routing (paid users)", () => {
    function Location() {
      return <span data-testid="location">{useLocation().pathname}</span>;
    }

    it("routes a Creator viewing the lower-ranked Pro card to /billing, never starting checkout", async () => {
      mockAccount(buildAccount("creator"));
      render(
        <MemoryRouter>
          <Pricing />
          <Location />
        </MemoryRouter>
      );

      await userEvent.click(screen.getAllByRole("button", { name: "Manage subscription" })[0]);
      expect(screen.getByTestId("location")).toHaveTextContent("/billing");
      expect(api.createCheckout).not.toHaveBeenCalled();
    });

    it("routes a Pro user viewing the lower-ranked Free card to /billing (cancellation lives there, not a one-click downgrade)", async () => {
      mockAccount(buildAccount("pro"));
      render(
        <MemoryRouter>
          <Pricing />
          <Location />
        </MemoryRouter>
      );

      await userEvent.click(cardButton("Manage subscription"));
      expect(screen.getByTestId("location")).toHaveTextContent("/billing");
    });
  });

  describe("no regression to Paddle checkout / change-plan actions", () => {
    it("routes an already-subscribed user's genuine upgrade to native billing without a fresh checkout", async () => {
      mockAccount(buildAccount("pro"));
      function Location() { return <span data-testid="location">{useLocation().pathname}</span>; }
      render(<MemoryRouter><Pricing /><Location /></MemoryRouter>);
      await userEvent.click(screen.getByRole("button", { name: "Upgrade" }));
      expect(screen.getByTestId("location")).toHaveTextContent("/billing");
      expect(api.createCheckout).not.toHaveBeenCalled();
    });

    it("starts a fresh Paddle checkout for a Free-plan account with no active subscription", async () => {
      vi.mocked(api.createCheckout).mockResolvedValue(undefined as never);
      mockAccount(buildAccount("free", "none"));
      renderPricing();
      await userEvent.click(screen.getAllByRole("button", { name: "Upgrade" })[0]);
      expect(api.createCheckout).toHaveBeenCalledWith("pro", "monthly");
    });
  });

  describe("Arabic labels", () => {
    it("render correctly for a Creator user (current / manage-subscription copy)", async () => {
      await i18n.changeLanguage("ar");
      mockAccount(buildAccount("creator"));
      renderPricing();

      expect(screen.getAllByText("الخطة الحالية")).toHaveLength(1);
      expect(screen.getAllByText("إدارة الاشتراك")).toHaveLength(2);
      expect(screen.queryByText("ترقية")).not.toBeInTheDocument();

      await i18n.changeLanguage("en");
    });
  });
});
