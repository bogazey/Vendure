import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Pricing from "./Pricing";
import { api } from "../services/api";
import { useAuth } from "../context/AuthContext";

vi.mock("../context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("../services/api", () => ({
  api: { createCheckout: vi.fn() },
  ApiError: class ApiError extends Error {},
}));

describe("Pricing", () => {
  it("shows monthly prices by default and switches to annual on toggle", async () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    render(
      <MemoryRouter>
        <Pricing />
      </MemoryRouter>
    );

    expect(screen.getByText("$4.99")).toBeInTheDocument();
    expect(screen.getByText("$9.99")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Annual/ }));

    expect(screen.getByText("$49")).toBeInTheDocument();
    expect(screen.getByText("$99")).toBeInTheDocument();
  });

  it("marks the account's current plan and disables its button", () => {
    vi.mocked(useAuth).mockReturnValue({
      account: {
        user: { id: "u1", email: "a@example.com", email_verified: true, role: "user", status: "active", created_at: "2026-01-01T00:00:00Z" },
        subscription: { plan: "pro", status: "active", billing_period: "monthly", current_period_start: null, current_period_end: null, cancel_at_period_end: false },
        usage: { plan: "pro", period_start: "2026-01-01T00:00:00Z", period_end: "2026-02-01T00:00:00Z", credits_included: 150, credits_used: 0, credits_remaining: 150, daily_free_downloads_used: null, daily_free_downloads_remaining: null },
        features: { plan: "pro", max_resolution_height: null, can_use_4k: true, can_use_batch: true, can_use_advanced_formats: true, can_use_clip_range: true, can_use_browser_cookies: true, can_use_original_container: true, can_use_creator_tools: false, ads_enabled: false, queue_priority: 5, monthly_credits: 150, daily_free_downloads: null },
      },
      loading: false,
      refresh: vi.fn(),
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
    });
    render(
      <MemoryRouter>
        <Pricing />
      </MemoryRouter>
    );
    const currentPlanButtons = screen.getAllByText("Current plan");
    expect(currentPlanButtons).toHaveLength(1);
    expect(currentPlanButtons[0].closest("button")).toBeDisabled();
  });
  it("routes an existing subscriber to native billing without checkout", async () => {
    vi.mocked(useAuth).mockReturnValue({
      account: {
        user: { id: "u1", email: "a@example.com", email_verified: true, role: "user", status: "active", created_at: "2026-01-01T00:00:00Z" },
        subscription: { plan: "pro", status: "active", billing_period: "monthly", current_period_start: null, current_period_end: null, cancel_at_period_end: false },
        usage: { plan: "pro", period_start: "2026-01-01T00:00:00Z", period_end: "2026-02-01T00:00:00Z", credits_included: 150, credits_used: 0, credits_remaining: 150, daily_free_downloads_used: null, daily_free_downloads_remaining: null },
        features: { plan: "pro", max_resolution_height: null, can_use_4k: true, can_use_batch: true, can_use_advanced_formats: true, can_use_clip_range: true, can_use_browser_cookies: true, can_use_original_container: true, can_use_creator_tools: false, ads_enabled: false, queue_priority: 5, monthly_credits: 150, daily_free_downloads: null },
      },
      loading: false,
      refresh: vi.fn(),
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
    });
    function Location() { return <span data-testid="location">{useLocation().pathname}</span>; }
    render(<MemoryRouter><Pricing /><Location /></MemoryRouter>);
    await userEvent.click(screen.getByRole("button", { name: "Upgrade" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/billing");
    expect(api.createCheckout).not.toHaveBeenCalled();
  });

});
