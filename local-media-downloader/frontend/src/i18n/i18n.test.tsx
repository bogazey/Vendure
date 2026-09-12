import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Header from "../components/Header";
import HeroUrlInput from "../components/HeroUrlInput";
import Sidebar from "../components/Sidebar";
import AdminOverview from "../pages/admin/AdminOverview";
import i18n, { LANGUAGE_STORAGE_KEY } from ".";
import { useAuth } from "../context/AuthContext";
import { api } from "../services/api";

vi.mock("../context/AuthContext", () => ({ useAuth: vi.fn() }));
vi.mock("../services/api", () => ({
  api: { adminGetOverview: vi.fn(), adminGetHealth: vi.fn(), adminAnalyticsOverview: vi.fn() },
  ApiError: class ApiError extends Error {},
}));

const signedOut = { account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() };

describe("English and Arabic internationalization", () => {
  it("defaults to English and switches document direction and navigation to Arabic", async () => {
    vi.mocked(useAuth).mockReturnValue(signedOut);
    localStorage.removeItem(LANGUAGE_STORAGE_KEY);
    await i18n.changeLanguage("en");
    render(<MemoryRouter><Header health={null} healthError={false} /></MemoryRouter>);

    expect(document.documentElement).toHaveAttribute("lang", "en");
    expect(document.documentElement).toHaveAttribute("dir", "ltr");
    expect(screen.getAllByText("Features").length).toBeGreaterThan(0);

    await userEvent.click(screen.getAllByRole("button", { name: "العربية" })[0]);
    expect(document.documentElement).toHaveAttribute("lang", "ar");
    expect(document.documentElement).toHaveAttribute("dir", "rtl");
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("ar");
    expect(screen.getAllByText("المزايا").length).toBeGreaterThan(0);
    expect(screen.getAllByText("الأسعار").length).toBeGreaterThan(0);
  });

  it("switches back to English and keeps URL input LTR in Arabic", async () => {
    vi.mocked(useAuth).mockReturnValue(signedOut);
    await i18n.changeLanguage("ar");
    const { rerender } = render(<MemoryRouter><HeroUrlInput /></MemoryRouter>);
    expect(screen.getByRole("textbox")).toHaveAttribute("dir", "ltr");

    await i18n.changeLanguage("en");
    rerender(<MemoryRouter><Header health={null} healthError={false} /></MemoryRouter>);
    expect(document.documentElement).toHaveAttribute("lang", "en");
    expect(document.documentElement).toHaveAttribute("dir", "ltr");
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("en");
  });

  it("translates authenticated application navigation", async () => {
    vi.mocked(useAuth).mockReturnValue({
      account: { user: { role: "user" } },
      logout: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>);
    await i18n.changeLanguage("ar");
    render(<MemoryRouter><Sidebar /></MemoryRouter>);

    expect(screen.getByText("تنزيلاتي")).toBeInTheDocument();
    expect(screen.getByText("الإعدادات")).toBeInTheDocument();
    expect(screen.getByText("الفوترة")).toBeInTheDocument();
  });

  it("renders the admin panel in Arabic with RTL direction and translated tabs", async () => {
    vi.mocked(useAuth).mockReturnValue({
      account: { user: { role: "admin" } },
      logout: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>);
    vi.mocked(api.adminGetOverview).mockResolvedValue({
      total_users: 5,
      active_users: 5,
      disabled_users: 0,
      paid_subscribers: 1,
      free_count: 4,
      pro_count: 1,
      creator_count: 0,
      gifted_subscribers: 0,
      credits_consumed_current_period: 12,
      recent_billing_failures: [],
      recent_admin_actions: [],
    });
    vi.mocked(api.adminGetHealth).mockResolvedValue({
      status: "ok",
      ytdlp_version: "2026.01.01",
      ffmpeg_available: true,
      download_dir_writable: true,
      database_ok: true,
    });
    vi.mocked(api.adminAnalyticsOverview).mockResolvedValue({
      range: "today", visitors: 0, page_views: 0, downloads_completed: 0,
      new_users: 0, paid_conversions: 0, active_now: 0, download_success_rate: null,
    });
    await i18n.changeLanguage("ar");
    render(<MemoryRouter><AdminOverview /></MemoryRouter>);

    expect(document.documentElement).toHaveAttribute("dir", "rtl");
    expect(screen.getByText("الإدارة")).toBeInTheDocument();
    expect(screen.getByText("نظرة عامة")).toBeInTheDocument();
    expect(screen.getByText("المستخدمون")).toBeInTheDocument();
    expect(screen.getByText("الفوترة")).toBeInTheDocument();
    expect(await screen.findByText("إجمالي المستخدمين")).toBeInTheDocument();
    expect(screen.getAllByText("5").length).toBeGreaterThan(0);

    await i18n.changeLanguage("en");
  });
});
