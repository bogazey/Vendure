import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Dashboard from "./Dashboard";
import i18n from "../i18n";
import { useAuth } from "../context/AuthContext";
import { useDownloadProgress } from "../hooks/useDownloadProgress";
import { api, triggerFileDownload } from "../services/api";
import type { AccountOut } from "../types/commercial";
import type { AnalyzeResponse, DownloadJobOut } from "../types/api";

vi.mock("../context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("../hooks/useDownloadProgress", () => ({
  useDownloadProgress: vi.fn(),
}));

vi.mock("../services/api", () => ({
  api: {
    analyze: vi.fn(),
    createDownload: vi.fn(),
    cancelDownload: vi.fn(),
    getGuestQuota: vi.fn(),
    listAdPlacements: vi.fn().mockResolvedValue([]),
  },
  downloadFileUrl: (id: string) => `/api/downloads/${id}/file`,
  triggerFileDownload: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    technical?: string | null;
    code?: string | null;
    constructor(message: string, status: number, technical?: string | null, code?: string | null) {
      super(message);
      this.status = status;
      this.technical = technical;
      this.code = code;
    }
  },
}));

function makeAnalyzeResponse(): AnalyzeResponse {
  return {
    url: "https://www.youtube.com/watch?v=abc123",
    platform: "youtube",
    media_type: "video",
    id: "abc123",
    title: "A Test Video",
    uploader: "someone",
    thumbnail: null,
    duration: 120,
    description: null,
    image_url: null,
    image_width: null,
    image_height: null,
    image_ext: null,
    is_playlist: false,
    playlist_title: null,
    playlist_count: null,
    playlist_entries_preview: [],
    media_items: [],
    video_presets: [{ key: "360", label: "360p", kind: "video", available: true, height: 360, expected_container: "mp4", will_transcode: false }],
    audio_presets: [{ key: "best", label: "Best", kind: "audio", available: true, height: null, expected_container: "m4a", will_transcode: false }],
    advanced_formats: [],
  };
}

function makeAccount(): AccountOut {
  return {
    user: { id: "u1", email: "a@example.com", email_verified: true, role: "user", status: "active", created_at: "2026-01-01T00:00:00Z" },
    subscription: { plan: "free", status: "none", billing_period: null, current_period_start: null, current_period_end: null, cancel_at_period_end: false },
    usage: { plan: "free", period_start: "2026-01-01T00:00:00Z", period_end: "2026-02-01T00:00:00Z", credits_included: 0, credits_used: 0, credits_remaining: 0, daily_free_downloads_used: 1, daily_free_downloads_remaining: 4 },
    features: { plan: "free", max_resolution_height: 720, can_use_4k: false, can_use_batch: false, can_use_advanced_formats: false, can_use_clip_range: false, can_use_browser_cookies: false, can_use_original_container: false, can_use_creator_tools: false, ads_enabled: true, queue_priority: 1, monthly_credits: null, daily_free_downloads: 5 },
  };
}

function makeJob(overrides: Partial<DownloadJobOut> = {}): DownloadJobOut {
  return {
    id: "job-1",
    url: "https://www.youtube.com/watch?v=abc123",
    platform: "youtube",
    title: "A Test Video",
    uploader: "someone",
    thumbnail: null,
    media_type: "video",
    stage: "queued",
    progress_percent: 0,
    speed_bps: null,
    downloaded_bytes: null,
    total_bytes: null,
    eta_seconds: null,
    filepath: null,
    error_message: null,
    created_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    ...overrides,
  };
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Dashboard />
    </MemoryRouter>
  );
}

describe("Dashboard guest download flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useDownloadProgress).mockReturnValue({ jobs: [], connected: true });
    vi.mocked(api.listAdPlacements).mockResolvedValue([]);
  });

  it("shows the no-account-required banner for a signed-out guest with a full allowance", async () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    vi.mocked(api.getGuestQuota).mockResolvedValue({ remaining: 2, limit: 2 });

    renderDashboard();

    expect(await screen.findByText("2 free downloads — no account required")).toBeInTheDocument();
  });

  it("shows the one-remaining message after the guest's first download", async () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    vi.mocked(api.getGuestQuota).mockResolvedValue({ remaining: 1, limit: 2 });

    renderDashboard();

    expect(await screen.findByText("1 free download remaining")).toBeInTheDocument();
  });

  it("replaces the format selector with a signup CTA once the guest allowance is exhausted, without navigating away", async () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    vi.mocked(api.getGuestQuota).mockResolvedValue({ remaining: 0, limit: 2 });
    vi.mocked(api.analyze).mockResolvedValue(makeAnalyzeResponse());

    renderDashboard();
    await screen.findByText("You've used your free downloads");

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Paste a YouTube, TikTok, Instagram or Facebook link…"), "https://www.youtube.com/watch?v=abc123");
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    const cta = await screen.findByRole("link", { name: "Create free account" });
    expect(cta).toHaveAttribute("href", "/signup");
    // The bug being fixed: clicking Download must never redirect away from
    // /dashboard on its own - only this explicit, visible CTA link does,
    // and only once the visitor has actually used up their free tries.
    expect(screen.queryByRole("button", { name: "Start Download" })).not.toBeInTheDocument();
    expect(api.createDownload).not.toHaveBeenCalled();
  });

  it("shows the format selector (not the CTA) while the guest still has downloads left", async () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    vi.mocked(api.getGuestQuota).mockResolvedValue({ remaining: 1, limit: 2 });
    vi.mocked(api.analyze).mockResolvedValue(makeAnalyzeResponse());

    renderDashboard();
    await screen.findByText("1 free download remaining");

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Paste a YouTube, TikTok, Instagram or Facebook link…"), "https://www.youtube.com/watch?v=abc123");
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    expect(await screen.findByRole("button", { name: "Start Download" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Create free account" })).not.toBeInTheDocument();
  });

  it("shows a friendly message and the CTA if the server rejects a download as quota-exceeded", async () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    vi.mocked(api.getGuestQuota).mockResolvedValueOnce({ remaining: 1, limit: 2 }).mockResolvedValueOnce({ remaining: 0, limit: 2 });
    vi.mocked(api.analyze).mockResolvedValue(makeAnalyzeResponse());
    const { ApiError } = await import("../services/api");
    vi.mocked(api.createDownload).mockRejectedValue(new ApiError("Guest quota exceeded", 402, null, "GUEST_QUOTA_EXCEEDED"));

    renderDashboard();
    await screen.findByText("1 free download remaining");

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("Paste a YouTube, TikTok, Instagram or Facebook link…"), "https://www.youtube.com/watch?v=abc123");
    await user.click(screen.getByRole("button", { name: "Analyze" }));
    await user.click(await screen.findByRole("button", { name: "Start Download" }));

    expect(await screen.findByText("You've used both free downloads on this device. Create a free account to keep going.")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Create free account" })).toBeInTheDocument();
  });

  it("never fetches or shows a guest quota for a signed-in account", async () => {
    vi.mocked(useAuth).mockReturnValue({ account: makeAccount(), loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });

    renderDashboard();

    // Give any stray effects a tick, then assert the guest UI never appears.
    await new Promise((r) => setTimeout(r, 0));
    expect(api.getGuestQuota).not.toHaveBeenCalled();
    expect(screen.queryByText("2 free downloads — no account required")).not.toBeInTheDocument();
    expect(screen.queryByText(/free download/)).not.toBeInTheDocument();
  });

  it("renders the guest banner in Arabic", async () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    vi.mocked(api.getGuestQuota).mockResolvedValue({ remaining: 2, limit: 2 });

    await i18n.changeLanguage("ar");
    renderDashboard();

    expect(await screen.findByText("تنزيلان مجانيان — بلا حاجة لحساب")).toBeInTheDocument();
    await i18n.changeLanguage("en");
  });
});

describe("Dashboard auto-download on job completion", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listAdPlacements).mockResolvedValue([]);
    vi.mocked(useAuth).mockReturnValue({
      account: makeAccount(), loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn(),
    });
  });

  async function startDownloadFromDashboard() {
    const user = userEvent.setup();
    vi.mocked(api.analyze).mockResolvedValue(makeAnalyzeResponse());
    await user.type(
      screen.getByPlaceholderText("Paste a YouTube, TikTok, Instagram or Facebook link…"),
      "https://www.youtube.com/watch?v=abc123",
    );
    await user.click(screen.getByRole("button", { name: "Analyze" }));
    await user.click(await screen.findByRole("button", { name: "Start Download" }));
  }

  it("auto-downloads once when a job created from this page transitions to completed", async () => {
    vi.mocked(useDownloadProgress).mockReturnValue({ jobs: [], connected: true });
    vi.mocked(api.createDownload).mockResolvedValue(makeJob({ id: "job-1", stage: "queued" }));

    const { rerender } = renderDashboard();
    await startDownloadFromDashboard();
    expect(triggerFileDownload).not.toHaveBeenCalled();

    vi.mocked(useDownloadProgress).mockReturnValue({
      jobs: [makeJob({ id: "job-1", stage: "completed", filepath: "/data/job-1.mp4", progress_percent: 100 })],
      connected: true,
    });
    rerender(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Dashboard />
      </MemoryRouter>,
    );

    expect(triggerFileDownload).toHaveBeenCalledTimes(1);
    expect(triggerFileDownload).toHaveBeenCalledWith("job-1");
  });

  it("does not auto-download again on repeated completed updates for the same job (SSE re-emits, re-renders)", async () => {
    vi.mocked(useDownloadProgress).mockReturnValue({ jobs: [], connected: true });
    vi.mocked(api.createDownload).mockResolvedValue(makeJob({ id: "job-1", stage: "queued" }));

    const { rerender } = renderDashboard();
    await startDownloadFromDashboard();

    const completed = makeJob({ id: "job-1", stage: "completed", filepath: "/data/job-1.mp4" });
    vi.mocked(useDownloadProgress).mockReturnValue({ jobs: [completed], connected: true });
    rerender(<MemoryRouter initialEntries={["/dashboard"]}><Dashboard /></MemoryRouter>);
    expect(triggerFileDownload).toHaveBeenCalledTimes(1);

    // A fresh array (as a new SSE frame or a stray re-render would produce),
    // same job, still completed - must not fire a second time.
    vi.mocked(useDownloadProgress).mockReturnValue({ jobs: [{ ...completed }], connected: true });
    rerender(<MemoryRouter initialEntries={["/dashboard"]}><Dashboard /></MemoryRouter>);
    rerender(<MemoryRouter initialEntries={["/dashboard"]}><Dashboard /></MemoryRouter>);

    expect(triggerFileDownload).toHaveBeenCalledTimes(1);
  });

  it("does not auto-download a pre-existing completed job loaded from history on mount", async () => {
    vi.mocked(useDownloadProgress).mockReturnValue({
      jobs: [makeJob({ id: "old-job", stage: "completed", filepath: "/data/old-job.mp4" })],
      connected: true,
    });

    renderDashboard();
    await new Promise((r) => setTimeout(r, 0));

    expect(triggerFileDownload).not.toHaveBeenCalled();
    expect(api.createDownload).not.toHaveBeenCalled();
  });

  it("does not auto-download a failed job", async () => {
    vi.mocked(useDownloadProgress).mockReturnValue({ jobs: [], connected: true });
    vi.mocked(api.createDownload).mockResolvedValue(makeJob({ id: "job-1", stage: "queued" }));

    const { rerender } = renderDashboard();
    await startDownloadFromDashboard();

    vi.mocked(useDownloadProgress).mockReturnValue({
      jobs: [makeJob({ id: "job-1", stage: "failed", error_message: "boom" })],
      connected: true,
    });
    rerender(<MemoryRouter initialEntries={["/dashboard"]}><Dashboard /></MemoryRouter>);

    expect(triggerFileDownload).not.toHaveBeenCalled();
  });

  it("does not auto-download a job that is still processing", async () => {
    vi.mocked(useDownloadProgress).mockReturnValue({ jobs: [], connected: true });
    vi.mocked(api.createDownload).mockResolvedValue(makeJob({ id: "job-1", stage: "queued" }));

    const { rerender } = renderDashboard();
    await startDownloadFromDashboard();

    vi.mocked(useDownloadProgress).mockReturnValue({
      jobs: [makeJob({ id: "job-1", stage: "downloading", progress_percent: 42 })],
      connected: true,
    });
    rerender(<MemoryRouter initialEntries={["/dashboard"]}><Dashboard /></MemoryRouter>);

    expect(triggerFileDownload).not.toHaveBeenCalled();
  });

  it("auto-downloads each of two newly-created jobs exactly once when each completes", async () => {
    vi.mocked(useDownloadProgress).mockReturnValue({ jobs: [], connected: true });
    vi.mocked(api.createDownload)
      .mockResolvedValueOnce(makeJob({ id: "job-1", stage: "queued" }))
      .mockResolvedValueOnce(makeJob({ id: "job-2", stage: "queued" }));

    const { rerender } = renderDashboard();
    await startDownloadFromDashboard();
    await startDownloadFromDashboard();

    vi.mocked(useDownloadProgress).mockReturnValue({
      jobs: [
        makeJob({ id: "job-1", stage: "completed", filepath: "/data/job-1.mp4" }),
        makeJob({ id: "job-2", stage: "completed", filepath: "/data/job-2.mp4" }),
      ],
      connected: true,
    });
    rerender(<MemoryRouter initialEntries={["/dashboard"]}><Dashboard /></MemoryRouter>);

    expect(triggerFileDownload).toHaveBeenCalledTimes(2);
    expect(triggerFileDownload).toHaveBeenCalledWith("job-1");
    expect(triggerFileDownload).toHaveBeenCalledWith("job-2");
  });

  it("keeps a working manual Download again action on a completed job", async () => {
    vi.mocked(useDownloadProgress).mockReturnValue({
      jobs: [makeJob({ id: "old-job", stage: "completed", filepath: "/data/old-job.mp4" })],
      connected: true,
    });

    renderDashboard();

    const link = await screen.findByRole("link", { name: "Download again" });
    expect(link).toHaveAttribute("href", "/api/downloads/old-job/file");
  });

  it("does not re-download a session job after a full remount (simulated page refresh)", async () => {
    vi.mocked(useDownloadProgress).mockReturnValue({ jobs: [], connected: true });
    vi.mocked(api.createDownload).mockResolvedValue(makeJob({ id: "job-1", stage: "queued" }));

    const { rerender, unmount } = renderDashboard();
    await startDownloadFromDashboard();

    vi.mocked(useDownloadProgress).mockReturnValue({
      jobs: [makeJob({ id: "job-1", stage: "completed", filepath: "/data/job-1.mp4" })],
      connected: true,
    });
    rerender(<MemoryRouter initialEntries={["/dashboard"]}><Dashboard /></MemoryRouter>);
    expect(triggerFileDownload).toHaveBeenCalledTimes(1);

    // A real refresh throws away all in-memory state and mounts a brand new
    // Dashboard instance - the same completed job now just looks like
    // ordinary history on the fresh mount, exactly like the "pre-existing
    // completed job" case above.
    unmount();
    renderDashboard();
    await new Promise((r) => setTimeout(r, 0));

    expect(triggerFileDownload).toHaveBeenCalledTimes(1);
  });
});
