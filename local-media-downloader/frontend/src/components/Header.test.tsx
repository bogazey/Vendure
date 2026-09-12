import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Header from "./Header";
import { useAuth } from "../context/AuthContext";
import type { AccountOut } from "../types/commercial";

vi.mock("../context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

function proAccount(): AccountOut {
  return {
    user: { id: "u1", email: "pro-user@example.com", email_verified: true, role: "user", status: "active", created_at: "2026-01-01T00:00:00Z" },
    subscription: { plan: "pro", status: "active", billing_period: "monthly", current_period_start: "2026-01-01T00:00:00Z", current_period_end: "2026-02-01T00:00:00Z", cancel_at_period_end: false, provider: "paddle" },
    usage: { plan: "pro", period_start: "2026-01-01T00:00:00Z", period_end: "2026-02-01T00:00:00Z", credits_included: 150, credits_used: 12, credits_remaining: 138, daily_free_downloads_used: null, daily_free_downloads_remaining: null },
    features: { plan: "pro", max_resolution_height: null, can_use_4k: true, can_use_batch: true, can_use_advanced_formats: true, can_use_clip_range: true, can_use_browser_cookies: true, can_use_original_container: true, can_use_creator_tools: false, ads_enabled: false, queue_priority: 5, monthly_credits: 150, daily_free_downloads: null },
  };
}

describe("Header", () => {
  it("shows Sign in / Get started when signed out", () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    render(
      <MemoryRouter>
        <Header health={null} healthError={false} />
      </MemoryRouter>
    );
    expect(screen.getByText("Sign in")).toBeInTheDocument();
    expect(screen.getByText("Get started")).toBeInTheDocument();
  });

  it("shows the plan badge and account menu when signed in", () => {
    vi.mocked(useAuth).mockReturnValue({ account: proAccount(), loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    render(
      <MemoryRouter>
        <Header health={null} healthError={false} />
      </MemoryRouter>
    );
    expect(screen.getByText("Pro")).toBeInTheDocument();
    expect(screen.getByText("pro-user@example.com")).toBeInTheDocument();
    expect(screen.queryByText("Sign in")).not.toBeInTheDocument();
  });

  it("shows credits-remaining usage in the account menu", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    vi.mocked(useAuth).mockReturnValue({ account: proAccount(), loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    render(
      <MemoryRouter>
        <Header health={null} healthError={false} />
      </MemoryRouter>
    );
    const user = userEvent.setup();
    await user.click(screen.getByText("pro-user@example.com"));
    expect(screen.getByText(/138 credit\(s\) remaining/)).toBeInTheDocument();
  });
});
