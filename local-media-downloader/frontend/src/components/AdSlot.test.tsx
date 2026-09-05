import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdSlot from "./AdSlot";
import { useAuth } from "../context/AuthContext";
import { api } from "../services/api";
import type { AccountOut, AdPlacementOut } from "../types/commercial";

vi.mock("../context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("../services/api", () => ({
  api: { listAdPlacements: vi.fn() },
}));

function accountWith(overrides: Partial<AccountOut["features"]>): AccountOut {
  return {
    user: { id: "u1", email: "a@example.com", email_verified: true, role: "user", status: "active", created_at: "2026-01-01T00:00:00Z" },
    subscription: { plan: "free", status: "none", billing_period: null, current_period_start: null, current_period_end: null, cancel_at_period_end: false },
    usage: { plan: "free", period_start: "2026-01-01T00:00:00Z", period_end: "2026-01-02T00:00:00Z", credits_included: null, credits_used: 0, credits_remaining: null, daily_free_downloads_used: 0, daily_free_downloads_remaining: 5 },
    features: { plan: "free", max_resolution_height: 720, can_use_4k: false, can_use_batch: false, can_use_advanced_formats: false, can_use_clip_range: false, can_use_browser_cookies: false, can_use_original_container: false, can_use_creator_tools: false, ads_enabled: true, queue_priority: 1, monthly_credits: null, daily_free_downloads: 5, ...overrides },
  };
}

function placement(overrides: Partial<AdPlacementOut> = {}): AdPlacementOut {
  return { id: "LANDING_DOWNLOADER", enabled: true, provider: null, public_slot_id: null, ...overrides };
}

function mockAuth(account: AccountOut | null) {
  vi.mocked(useAuth).mockReturnValue({ account, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
}

describe("AdSlot", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a placeholder for a Free account when the placement is enabled", async () => {
    vi.mocked(api.listAdPlacements).mockResolvedValue([placement({ enabled: true })]);
    mockAuth(accountWith({}));
    render(<AdSlot placement="LANDING_DOWNLOADER" />);
    expect(await screen.findByText(/Ad space reserved/i)).toBeInTheDocument();
  });

  it("renders nothing for a Pro account (ads ineligible)", () => {
    mockAuth(accountWith({ ads_enabled: false }));
    const { container } = render(<AdSlot placement="LANDING_DOWNLOADER" />);
    expect(container).toBeEmptyDOMElement();
    expect(api.listAdPlacements).not.toHaveBeenCalled();
  });

  it("renders nothing when signed out", () => {
    mockAuth(null);
    const { container } = render(<AdSlot placement="LANDING_DOWNLOADER" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the placement is disabled", async () => {
    vi.mocked(api.listAdPlacements).mockResolvedValue([placement({ enabled: false })]);
    mockAuth(accountWith({}));
    const { container } = render(<AdSlot placement="LANDING_DOWNLOADER" />);
    await vi.waitFor(() => expect(api.listAdPlacements).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("fails gracefully (renders the neutral placeholder, not a fake ad) when no provider is configured", async () => {
    vi.mocked(api.listAdPlacements).mockResolvedValue([placement({ enabled: true, provider: null, public_slot_id: null })]);
    mockAuth(accountWith({}));
    render(<AdSlot placement="LANDING_DOWNLOADER" />);
    expect(await screen.findByText(/Ad space reserved/i)).toBeInTheDocument();
  });

  it("renders nothing for a placement id that doesn't exist in the registry", async () => {
    vi.mocked(api.listAdPlacements).mockResolvedValue([placement({ id: "DOWNLOAD_RESULT", enabled: true })]);
    mockAuth(accountWith({}));
    const { container } = render(<AdSlot placement="LANDING_DOWNLOADER" />);
    await vi.waitFor(() => expect(api.listAdPlacements).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
