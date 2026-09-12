import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ProtectedRoute, { AdminRoute, GuestAllowedRoute } from "./ProtectedRoute";
import { useAuth } from "../context/AuthContext";
import type { AccountOut } from "../types/commercial";

vi.mock("../context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

function baseAccount(role: "user" | "admin" = "user"): AccountOut {
  return {
    user: { id: "u1", email: "a@example.com", email_verified: true, role, status: "active", created_at: "2026-01-01T00:00:00Z" },
    subscription: { plan: "free", status: "none", billing_period: null, current_period_start: null, current_period_end: null, cancel_at_period_end: false, provider: "none" },
    usage: { plan: "free", period_start: "2026-01-01T00:00:00Z", period_end: "2026-01-02T00:00:00Z", credits_included: null, credits_used: 0, credits_remaining: null, daily_free_downloads_used: 0, daily_free_downloads_remaining: 5 },
    features: { plan: "free", max_resolution_height: 720, can_use_4k: false, can_use_batch: false, can_use_advanced_formats: false, can_use_clip_range: false, can_use_browser_cookies: false, can_use_original_container: false, can_use_creator_tools: false, ads_enabled: true, queue_priority: 1, monthly_credits: null, daily_free_downloads: 5 },
  };
}

function renderAt(path: string, ui: React.ReactElement) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<div>login page</div>} />
        <Route path="/dashboard" element={<div>dashboard fallback</div>} />
        <Route path="/protected" element={ui} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ProtectedRoute", () => {
  it("redirects to /login when signed out", () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    renderAt("/protected", <ProtectedRoute><div>secret content</div></ProtectedRoute>);
    expect(screen.getByText("login page")).toBeInTheDocument();
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("renders children when signed in", () => {
    vi.mocked(useAuth).mockReturnValue({ account: baseAccount(), loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    renderAt("/protected", <ProtectedRoute><div>secret content</div></ProtectedRoute>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("shows a loading state instead of redirecting while auth is resolving", () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: true, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    renderAt("/protected", <ProtectedRoute><div>secret content</div></ProtectedRoute>);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(screen.queryByText("login page")).not.toBeInTheDocument();
  });
});

describe("GuestAllowedRoute", () => {
  it("renders children for a signed-out visitor - no redirect to /login", () => {
    // This is the core of the guest-download-flow fix: /dashboard must
    // never bounce an anonymous visitor to signup/login just for visiting.
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    renderAt("/protected", <GuestAllowedRoute><div>downloader content</div></GuestAllowedRoute>);
    expect(screen.getByText("downloader content")).toBeInTheDocument();
    expect(screen.queryByText("login page")).not.toBeInTheDocument();
  });

  it("renders children for a signed-in user too", () => {
    vi.mocked(useAuth).mockReturnValue({ account: baseAccount(), loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    renderAt("/protected", <GuestAllowedRoute><div>downloader content</div></GuestAllowedRoute>);
    expect(screen.getByText("downloader content")).toBeInTheDocument();
  });

  it("shows a loading state instead of content while auth is still resolving", () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: true, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    renderAt("/protected", <GuestAllowedRoute><div>downloader content</div></GuestAllowedRoute>);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(screen.queryByText("downloader content")).not.toBeInTheDocument();
  });
});

describe("AdminRoute", () => {
  it("redirects a non-admin user to /dashboard", () => {
    vi.mocked(useAuth).mockReturnValue({ account: baseAccount("user"), loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    renderAt("/protected", <AdminRoute><div>admin content</div></AdminRoute>);
    expect(screen.getByText("dashboard fallback")).toBeInTheDocument();
    expect(screen.queryByText("admin content")).not.toBeInTheDocument();
  });

  it("renders children for an admin user", () => {
    vi.mocked(useAuth).mockReturnValue({ account: baseAccount("admin"), loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    renderAt("/protected", <AdminRoute><div>admin content</div></AdminRoute>);
    expect(screen.getByText("admin content")).toBeInTheDocument();
  });
});

describe("noindex on private routes", () => {
  // robots.txt Disallow entries alone would stop a crawler from ever
  // fetching these pages to see a noindex directive - the actual signal
  // is this live meta tag, applied centrally by the three route guards.
  it("marks a ProtectedRoute page noindex", () => {
    vi.mocked(useAuth).mockReturnValue({ account: baseAccount(), loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    renderAt("/protected", <ProtectedRoute><div>secret content</div></ProtectedRoute>);
    expect(document.head.querySelector('meta[name="robots"]')?.getAttribute("content")).toBe("noindex, nofollow");
  });

  it("marks a GuestAllowedRoute page (e.g. /dashboard) noindex even for a signed-out guest", () => {
    vi.mocked(useAuth).mockReturnValue({ account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    renderAt("/protected", <GuestAllowedRoute><div>downloader content</div></GuestAllowedRoute>);
    expect(document.head.querySelector('meta[name="robots"]')?.getAttribute("content")).toBe("noindex, nofollow");
  });

  it("marks an AdminRoute page noindex", () => {
    vi.mocked(useAuth).mockReturnValue({ account: baseAccount("admin"), loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() });
    renderAt("/protected", <AdminRoute><div>admin content</div></AdminRoute>);
    expect(document.head.querySelector('meta[name="robots"]')?.getAttribute("content")).toBe("noindex, nofollow");
  });
});
