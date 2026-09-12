import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import AdminOverview from "./AdminOverview";
import { api } from "../../services/api";
import type { AnalyticsOverviewOut } from "../../types/analytics";
import type { AdminHealthOut, AdminOverviewOut } from "../../types/commercial";

vi.mock("../../services/api", () => ({
  api: {
    adminGetOverview: vi.fn(),
    adminGetHealth: vi.fn(),
    adminAnalyticsOverview: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
}));

function makeAnalyticsOverview(overrides: Partial<AnalyticsOverviewOut> = {}): AnalyticsOverviewOut {
  return {
    range: "today",
    visitors: 5,
    page_views: 11,
    downloads_completed: 3,
    new_users: 1,
    paid_conversions: 0,
    active_now: 2,
    download_success_rate: 100,
    ...overrides,
  };
}

function makeOverview(overrides: Partial<AdminOverviewOut> = {}): AdminOverviewOut {
  return {
    total_users: 42,
    active_users: 40,
    disabled_users: 2,
    paid_subscribers: 12,
    free_count: 30,
    pro_count: 9,
    creator_count: 3,
    gifted_subscribers: 2,
    credits_consumed_current_period: 517,
    recent_billing_failures: [],
    recent_admin_actions: [],
    ...overrides,
  };
}

function makeHealth(overrides: Partial<AdminHealthOut> = {}): AdminHealthOut {
  return {
    status: "ok",
    database_ok: true,
    ffmpeg_available: true,
    ytdlp_version: "2026.01.01",
    download_dir_writable: true,
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminOverview />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.mocked(api.adminGetHealth).mockResolvedValue(makeHealth());
  vi.mocked(api.adminAnalyticsOverview).mockResolvedValue(makeAnalyticsOverview());
});

describe("AdminOverview", () => {
  it("renders stat tiles from the overview endpoint", async () => {
    vi.mocked(api.adminGetOverview).mockResolvedValue(makeOverview());
    renderPage();

    expect(await screen.findByText("42")).toBeInTheDocument();
    expect(screen.getByText("40")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("517")).toBeInTheDocument();
  });

  it("renders the analytics summary row (visitors/downloads/new users/success rate/active now) today", async () => {
    vi.mocked(api.adminGetOverview).mockResolvedValue(makeOverview());
    vi.mocked(api.adminAnalyticsOverview).mockResolvedValue(
      makeAnalyticsOverview({ visitors: 123, downloads_completed: 45, new_users: 6, active_now: 7, download_success_rate: 92.5 })
    );
    renderPage();

    expect(await screen.findByText("123")).toBeInTheDocument();
    expect(screen.getByText("45")).toBeInTheDocument();
    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("92.5%")).toBeInTheDocument();
  });

  it("still renders the overview even if the analytics summary fails to load", async () => {
    vi.mocked(api.adminGetOverview).mockResolvedValue(makeOverview());
    vi.mocked(api.adminAnalyticsOverview).mockRejectedValue(new Error("boom"));
    renderPage();

    expect(await screen.findByText("42")).toBeInTheDocument();
  });

  it("shows recent billing failures and admin actions when present", async () => {
    vi.mocked(api.adminGetOverview).mockResolvedValue(
      makeOverview({
        recent_billing_failures: [
          {
            provider_event_id: "evt-1",
            event_type: "transaction.payment_failed",
            processed_at: "2026-01-02T00:00:00Z",
            status: "failed",
            user_id: "user-9",
            user_email: "failed@example.com",
          },
        ],
        recent_admin_actions: [
          {
            id: "log-1",
            admin_id: "admin-1",
            admin_email: "admin@example.com",
            action: "grant_credits",
            target_user_id: "user-9",
            target_email: "failed@example.com",
            details: { credits: 10, reason: "support" },
            created_at: "2026-01-02T00:00:00Z",
          },
        ],
      })
    );
    renderPage();

    const matches = await screen.findAllByText("failed@example.com");
    expect(matches.length).toBe(2);
  });

  it("shows an empty-state message when there are no failures or actions", async () => {
    vi.mocked(api.adminGetOverview).mockResolvedValue(makeOverview());
    renderPage();

    expect(await screen.findByText(/no billing failures recorded/i)).toBeInTheDocument();
    expect(screen.getByText(/no admin actions recorded/i)).toBeInTheDocument();
  });
});
