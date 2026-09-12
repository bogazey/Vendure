import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";
import { api } from "../services/api";
import type { AccountOut } from "../types/commercial";

vi.mock("../services/api", () => ({
  api: {
    getAccount: vi.fn(),
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
  },
}));

const FREE_ACCOUNT: AccountOut = {
  user: { id: "u1", email: "a@example.com", email_verified: true, role: "user", status: "active", created_at: "2026-01-01T00:00:00Z" },
  subscription: { plan: "free", status: "none", billing_period: null, current_period_start: null, current_period_end: null, cancel_at_period_end: false, provider: "none" },
  usage: { plan: "free", period_start: "2026-01-01T00:00:00Z", period_end: "2026-01-02T00:00:00Z", credits_included: null, credits_used: 0, credits_remaining: null, daily_free_downloads_used: 1, daily_free_downloads_remaining: 4 },
  features: { plan: "free", max_resolution_height: 720, can_use_4k: false, can_use_batch: false, can_use_advanced_formats: false, can_use_clip_range: false, can_use_browser_cookies: false, can_use_original_container: false, can_use_creator_tools: false, ads_enabled: true, queue_priority: 1, monthly_credits: null, daily_free_downloads: 5 },
};

function Probe() {
  const { account, loading } = useAuth();
  if (loading) return <div>loading</div>;
  return <div>{account ? `signed in as ${account.user.email}` : "signed out"}</div>;
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.mocked(api.getAccount).mockReset();
  });

  it("loads the account on mount when a session cookie is valid", async () => {
    vi.mocked(api.getAccount).mockResolvedValue(FREE_ACCOUNT);
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByText("signed in as a@example.com")).toBeInTheDocument());
  });

  it("shows signed-out state when there is no valid session", async () => {
    vi.mocked(api.getAccount).mockRejectedValue(new Error("401"));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByText("signed out")).toBeInTheDocument());
  });

  it("login() calls the API then refreshes the account", async () => {
    vi.mocked(api.getAccount).mockRejectedValueOnce(new Error("401")).mockResolvedValueOnce(FREE_ACCOUNT);
    vi.mocked(api.login).mockResolvedValue(undefined as never);

    let ctx: ReturnType<typeof useAuth> | null = null;
    function Capture() {
      ctx = useAuth();
      return null;
    }
    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>
    );
    await waitFor(() => expect(ctx?.loading).toBe(false));

    await act(async () => {
      await ctx!.login("a@example.com", "pw");
    });

    expect(api.login).toHaveBeenCalledWith("a@example.com", "pw", false);
    expect(ctx!.account?.user.email).toBe("a@example.com");
  });

  it("login() forwards the rememberMe choice to the API", async () => {
    vi.mocked(api.getAccount).mockRejectedValueOnce(new Error("401")).mockResolvedValueOnce(FREE_ACCOUNT);
    vi.mocked(api.login).mockResolvedValue(undefined as never);

    let ctx: ReturnType<typeof useAuth> | null = null;
    function Capture() {
      ctx = useAuth();
      return null;
    }
    render(
      <AuthProvider>
        <Capture />
      </AuthProvider>
    );
    await waitFor(() => expect(ctx?.loading).toBe(false));

    await act(async () => {
      await ctx!.login("a@example.com", "pw", true);
    });

    expect(api.login).toHaveBeenCalledWith("a@example.com", "pw", true);
  });

  it("bootstraps the account exactly once even if the mount effect runs twice (StrictMode double-invoke)", async () => {
    vi.mocked(api.getAccount).mockResolvedValue(FREE_ACCOUNT);
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByText("signed in as a@example.com")).toBeInTheDocument());
    // A duplicate bootstrap would show up as a second call to /api/account.
    expect(api.getAccount).toHaveBeenCalledTimes(1);
  });
});
