import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AdSlot from "./AdSlot";
import { useAuth } from "../context/AuthContext";
import type { AccountOut } from "../types/commercial";

vi.mock("../context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

function accountWith(overrides: Partial<AccountOut["features"]>): AccountOut {
  return {
    user: { id: "u1", email: "a@example.com", email_verified: true, role: "user", status: "active", created_at: "2026-01-01T00:00:00Z" },
    subscription: { plan: "free", status: "none", billing_period: null, current_period_start: null, current_period_end: null, cancel_at_period_end: false },
    usage: { plan: "free", period_start: "2026-01-01T00:00:00Z", period_end: "2026-01-02T00:00:00Z", credits_included: null, credits_used: 0, credits_remaining: null, daily_free_downloads_used: 0, daily_free_downloads_remaining: 5 },
    features: { plan: "free", max_resolution_height: 720, can_use_4k: false, can_use_batch: false, can_use_advanced_formats: false, can_use_clip_range: false, can_use_browser_cookies: false, can_use_original_container: false, can_use_creator_tools: false, ads_enabled: true, queue_priority: 1, monthly_credits: null, daily_free_downloads: 5, ...overrides },
  };
}

describe("AdSlot", () => {
  it("renders a placeholder for a Free account (ads enabled)", () => {
    vi.mocked(useAuth).mockReturnValue({ account: accountWith({}), loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    render(<AdSlot placement="below-url-input" />);
    expect(screen.getByText(/Ad space reserved/i)).toBeInTheDocument();
  });

  it("renders nothing for a Pro account (ads disabled)", () => {
    vi.mocked(useAuth).mockReturnValue({
      account: accountWith({ ads_enabled: false }),
      loading: false,
      refresh: vi.fn(),
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
    });
    const { container } = render(<AdSlot placement="below-url-input" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when signed out", () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    const { container } = render(<AdSlot placement="below-url-input" />);
    expect(container).toBeEmptyDOMElement();
  });
});
