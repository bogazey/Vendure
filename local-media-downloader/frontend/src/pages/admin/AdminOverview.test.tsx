import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import AdminOverview from "./AdminOverview";
import { api } from "../../services/api";
import type { AdminOverviewOut } from "../../types/commercial";
import type { HealthResponse } from "../../types/api";

vi.mock("../../services/api", () => ({
  api: {
    adminGetOverview: vi.fn(),
    health: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
}));

function makeOverview(overrides: Partial<AdminOverviewOut> = {}): AdminOverviewOut {
  return {
    total_users: 42,
    active_users: 40,
    disabled_users: 2,
    paid_subscribers: 12,
    free_count: 30,
    pro_count: 9,
    creator_count: 3,
    credits_consumed_current_period: 517,
    recent_billing_failures: [],
    recent_admin_actions: [],
    ...overrides,
  };
}

function makeHealth(overrides: Partial<HealthResponse> = {}): HealthResponse {
  return {
    status: "ok",
    database_ok: true,
    ffmpeg_available: true,
    ffmpeg_path: "/usr/bin/ffmpeg",
    ytdlp_version: "2026.01.01",
    download_dir: "/data/downloads",
    download_dir_writable: true,
    ...overrides,
  } as HealthResponse;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminOverview />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.mocked(api.health).mockResolvedValue(makeHealth());
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
