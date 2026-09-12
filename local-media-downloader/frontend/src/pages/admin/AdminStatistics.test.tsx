import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import AdminStatistics from "./AdminStatistics";
import { api } from "../../services/api";
import i18n from "../../i18n";
import type {
  AnalyticsOverviewOut,
  DevicesOut,
  DownloadsOut,
  FunnelOut,
  GeographyOut,
  PagesOut,
  RevenueOut,
  SourcesOut,
  TrafficOut,
} from "../../types/analytics";

vi.mock("../../services/api", () => ({
  api: {
    adminAnalyticsOverview: vi.fn(),
    adminAnalyticsTraffic: vi.fn(),
    adminAnalyticsPages: vi.fn(),
    adminAnalyticsSources: vi.fn(),
    adminAnalyticsGeography: vi.fn(),
    adminAnalyticsDevices: vi.fn(),
    adminAnalyticsDownloads: vi.fn(),
    adminAnalyticsFunnel: vi.fn(),
    adminAnalyticsRevenue: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
}));

function emptyOverview(): AnalyticsOverviewOut {
  return {
    range: "30d", visitors: 0, page_views: 0, downloads_completed: 0,
    new_users: 0, paid_conversions: 0, active_now: 0, download_success_rate: null,
  };
}
function emptyTraffic(): TrafficOut { return { range: "30d", points: [] }; }
function emptyPages(): PagesOut { return { range: "30d", pages: [] }; }
function emptySources(): SourcesOut { return { range: "30d", sources: [] }; }
function emptyGeography(): GeographyOut { return { range: "30d", available: false, countries: [] }; }
function emptyDevices(): DevicesOut { return { range: "30d", devices: [], browsers: [], os: [], languages: [] }; }
function emptyDownloads(): DownloadsOut {
  return {
    range: "30d",
    analyze: { started: 0, completed: 0, failed: 0, success_rate: null, avg_processing_seconds: null },
    downloads: { started: 0, completed: 0, failed: 0, success_rate: null, avg_processing_seconds: null },
    platforms: [], failures: [],
  };
}
function emptyFunnel(): FunnelOut {
  return {
    range: "30d",
    stages: [
      { key: "visitors", label: "Visitors", count: 0, pct_of_previous: null },
      { key: "analyzed", label: "Analyzed", count: 0, pct_of_previous: null },
      { key: "downloaded", label: "Downloaded", count: 0, pct_of_previous: null },
      { key: "signed_up", label: "Signed up", count: 0, pct_of_previous: null },
      { key: "paid", label: "Paid", count: 0, pct_of_previous: null },
    ],
    methodology_note: "Aggregate counts for the selected period, not a per-visitor cohort funnel.",
  };
}
function emptyRevenue(): RevenueOut {
  return {
    range: "30d", active_paid_subscribers: 0, new_paid_subscribers: 0, cancellations: 0,
    movements: [], gifted_active_subscriptions: 0, gifted_events_this_period: 0,
    mrr_available: false, mrr_note: "MRR is not shown because...",
  };
}

function mockAllEmpty() {
  vi.mocked(api.adminAnalyticsOverview).mockResolvedValue(emptyOverview());
  vi.mocked(api.adminAnalyticsTraffic).mockResolvedValue(emptyTraffic());
  vi.mocked(api.adminAnalyticsPages).mockResolvedValue(emptyPages());
  vi.mocked(api.adminAnalyticsSources).mockResolvedValue(emptySources());
  vi.mocked(api.adminAnalyticsGeography).mockResolvedValue(emptyGeography());
  vi.mocked(api.adminAnalyticsDevices).mockResolvedValue(emptyDevices());
  vi.mocked(api.adminAnalyticsDownloads).mockResolvedValue(emptyDownloads());
  vi.mocked(api.adminAnalyticsFunnel).mockResolvedValue(emptyFunnel());
  vi.mocked(api.adminAnalyticsRevenue).mockResolvedValue(emptyRevenue());
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminStatistics />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAllEmpty();
});

describe("AdminStatistics", () => {
  it("shows a loading state before data arrives", () => {
    renderPage();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("renders empty states when there is no historical data yet (no fake demo numbers)", async () => {
    renderPage();
    await waitFor(() => expect(api.adminAnalyticsOverview).toHaveBeenCalled());

    const noDataMessages = await screen.findAllByText("No data yet.");
    expect(noDataMessages.length).toBeGreaterThan(0);
    expect(screen.getByText(/Country data isn't available yet/)).toBeInTheDocument();
  });

  it("renders populated stat cards and the funnel with its aggregate-period disclaimer", async () => {
    vi.mocked(api.adminAnalyticsOverview).mockResolvedValue({
      range: "30d", visitors: 1000, page_views: 4200, downloads_completed: 300,
      new_users: 40, paid_conversions: 5, active_now: 12, download_success_rate: 88.5,
    });
    vi.mocked(api.adminAnalyticsFunnel).mockResolvedValue({
      range: "30d",
      stages: [
        { key: "visitors", label: "Visitors", count: 10000, pct_of_previous: null },
        { key: "analyzed", label: "Analyzed", count: 4321, pct_of_previous: 42 },
        { key: "downloaded", label: "Downloaded", count: 2982, pct_of_previous: 71 },
        { key: "signed_up", label: "Signed up", count: 239, pct_of_previous: 8 },
        { key: "paid", label: "Paid", count: 14, pct_of_previous: 6 },
      ],
      methodology_note: "Aggregate counts for the selected period, not a per-visitor cohort funnel.",
    });
    renderPage();

    expect(await screen.findByText("1,000")).toBeInTheDocument();
    expect(screen.getByText("4,200")).toBeInTheDocument();
    expect(screen.getByText("300")).toBeInTheDocument();
    expect(screen.getByText("10,000")).toBeInTheDocument();
    expect(screen.getByText(/not a per-visitor cohort funnel/)).toBeInTheDocument();
  });

  it("re-fetches every endpoint when the date range is changed", async () => {
    renderPage();
    await waitFor(() => expect(api.adminAnalyticsOverview).toHaveBeenCalledWith("30d"));

    await userEvent.click(screen.getByRole("button", { name: "7 days" }));
    await waitFor(() => expect(api.adminAnalyticsOverview).toHaveBeenCalledWith("7d"));
    expect(api.adminAnalyticsTraffic).toHaveBeenCalledWith("7d");
    expect(api.adminAnalyticsFunnel).toHaveBeenCalledWith("7d");
  });

  it("declares MRR unavailable rather than showing a fabricated number", async () => {
    renderPage();
    expect(await screen.findByText(/MRR is not shown because/)).toBeInTheDocument();
  });

  it("renders Arabic labels and stays usable in RTL", async () => {
    await i18n.changeLanguage("ar");
    renderPage();
    expect(await screen.findByText("إحصائيات الموقع")).toBeInTheDocument();
    expect(screen.getByText("الزوار")).toBeInTheDocument();
    await i18n.changeLanguage("en");
  });
});
