import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import AdminUsers from "./AdminUsers";
import i18n from "../../i18n";
import { api } from "../../services/api";
import type { AdminUserOut } from "../../types/commercial";

vi.mock("../../services/api", () => ({
  api: {
    adminListUsers: vi.fn(),
    adminGrantCredits: vi.fn(),
    adminSetAccountStatus: vi.fn(),
    adminListAuditLog: vi.fn(),
    adminUpdateSubscription: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
}));

function makeUser(overrides: Partial<AdminUserOut> = {}): AdminUserOut {
  return {
    id: "user-1",
    email: "target@example.com",
    status: "active",
    role: "user",
    plan: "pro",
    subscription_status: "active",
    credits_used: 10,
    credits_included: 150,
    credits_bonus: 0,
    created_at: "2026-01-01T00:00:00Z",
    subscription_provider: "paddle",
    gifted_granted_at: null,
    gifted_granted_by_email: null,
    gifted_reason: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(api.adminListUsers).mockResolvedValue({ users: [makeUser()], total: 1 });
  vi.mocked(api.adminListAuditLog).mockResolvedValue([]);
});

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminUsers />
    </MemoryRouter>
  );
}

describe("AdminUsers", () => {
  it("loads and renders users on mount", async () => {
    renderPage();
    expect(await screen.findByText("target@example.com")).toBeInTheDocument();
    expect(screen.getByText("10 / 150")).toBeInTheDocument();
  });

  it("searches by the entered term", async () => {
    renderPage();
    await screen.findByText("target@example.com");
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/search/i), "target");
    await user.click(screen.getByRole("button", { name: /search/i }));

    await waitFor(() => {
      expect(api.adminListUsers).toHaveBeenLastCalledWith(expect.objectContaining({ search: "target" }));
    });
  });

  it("grants credits through the dialog", async () => {
    vi.mocked(api.adminGrantCredits).mockResolvedValue(makeUser({ credits_included: 180, credits_bonus: 30 }));
    renderPage();
    await screen.findByText("target@example.com");
    const user = userEvent.setup();

    await user.click(screen.getByText(/grant credits/i));
    const reasonInput = await screen.findByPlaceholderText(/support case/i);
    await user.type(reasonInput, "support case #1");
    await user.click(screen.getByRole("button", { name: /^Grant$/i }));

    await waitFor(() => {
      expect(api.adminGrantCredits).toHaveBeenCalledWith("user-1", 10, "support case #1");
    });
    expect(await screen.findByText(/30 bonus/i)).toBeInTheDocument();
  });

  it("requires confirmation before disabling an account, and does nothing on cancel", async () => {
    renderPage();
    await screen.findByText("target@example.com");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /^Disable$/i }));
    expect(await screen.findByText(/disable this account/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByText(/disable this account/i)).not.toBeInTheDocument();
    expect(api.adminSetAccountStatus).not.toHaveBeenCalled();
  });

  it("disables an account after confirming", async () => {
    vi.mocked(api.adminSetAccountStatus).mockResolvedValue(makeUser({ status: "disabled" }));
    renderPage();
    await screen.findByText("target@example.com");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /^Disable$/i }));
    const dialogConfirm = await screen.findAllByRole("button", { name: /^Disable$/i });
    await user.click(dialogConfirm[dialogConfirm.length - 1]);

    await waitFor(() => {
      expect(api.adminSetAccountStatus).toHaveBeenCalledWith("user-1", "disabled");
    });
    expect(await screen.findByRole("button", { name: /reactivate/i })).toBeInTheDocument();
  });

  it("opens a user detail view showing id, role, and credit breakdown", async () => {
    renderPage();
    await screen.findByText("target@example.com");
    const user = userEvent.setup();
    await user.click(screen.getByText("target@example.com"));

    expect(await screen.findByText("user-1")).toBeInTheDocument();
    expect(screen.getByText("150")).toBeInTheDocument();
  });

  it("shows the admin-specific Search button text in English, not the downloader's search string", async () => {
    renderPage();
    await screen.findByText("target@example.com");
    expect(screen.getByRole("button", { name: "Search" })).toBeInTheDocument();
    expect(screen.queryByText(/title, uploader, or url/i)).not.toBeInTheDocument();
  });

  it("shows the admin-specific Search button text in Arabic", async () => {
    await i18n.changeLanguage("ar");
    renderPage();
    await screen.findByText("target@example.com");
    expect(screen.getByRole("button", { name: "بحث" })).toBeInTheDocument();
  });
});

describe("AdminUsers gifted subscription controls", () => {
  it("blocks gifting controls for a user with an active paid Paddle subscription", async () => {
    vi.mocked(api.adminListUsers).mockResolvedValue({ users: [makeUser({ subscription_provider: "paddle" })], total: 1 });
    renderPage();
    await screen.findByText("target@example.com");
    const user = userEvent.setup();

    await user.click(screen.getByText("Manage subscription"));
    expect(await screen.findByText(/active paid Paddle subscription/)).toBeInTheDocument();
    expect(screen.queryByText("New plan")).not.toBeInTheDocument();
    expect(api.adminUpdateSubscription).not.toHaveBeenCalled();
  });

  it("shows editable gifting controls for a Free/eligible user and requires confirmation before mutating", async () => {
    vi.mocked(api.adminListUsers).mockResolvedValue({
      users: [makeUser({ plan: "free", subscription_status: "none", subscription_provider: "none" })],
      total: 1,
    });
    vi.mocked(api.adminUpdateSubscription).mockResolvedValue(
      makeUser({ plan: "pro", subscription_status: "active", subscription_provider: "gifted" })
    );
    renderPage();
    await screen.findByText("target@example.com");
    const user = userEvent.setup();

    await user.click(screen.getByText("Manage subscription"));
    expect(await screen.findByText("New plan")).toBeInTheDocument();
    expect(screen.getByText("This grants Loady access without charging the user.")).toBeInTheDocument();

    // The plan selector defaults to "pro" for a Free user - clicking the
    // grant button must show a confirmation step before calling the API.
    await user.click(screen.getByRole("button", { name: "Grant Gifted Subscription" }));
    expect(api.adminUpdateSubscription).not.toHaveBeenCalled();
    expect(await screen.findByText(/Grant this user/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Grant Gifted Subscription" }));
    await waitFor(() => {
      expect(api.adminUpdateSubscription).toHaveBeenCalledWith("user-1", "pro", undefined);
    });
  });

  it("offers Update Gifted Subscription for a Pro-gifted user changing to Creator", async () => {
    vi.mocked(api.adminListUsers).mockResolvedValue({
      users: [makeUser({ plan: "pro", subscription_status: "active", subscription_provider: "gifted" })],
      total: 1,
    });
    vi.mocked(api.adminUpdateSubscription).mockResolvedValue(
      makeUser({ plan: "creator", subscription_status: "active", subscription_provider: "gifted" })
    );
    renderPage();
    await screen.findByText("target@example.com");
    const user = userEvent.setup();

    await user.click(screen.getByText("Manage subscription"));
    await user.selectOptions(screen.getByRole("combobox"), "creator");
    await user.click(screen.getByRole("button", { name: "Update Gifted Subscription" }));
    await user.click(screen.getByRole("button", { name: "Update Gifted Subscription" }));

    await waitFor(() => {
      expect(api.adminUpdateSubscription).toHaveBeenCalledWith("user-1", "creator", undefined);
    });
  });

  it("offers Revoke Gifted Subscription that moves a gifted user back to Free", async () => {
    vi.mocked(api.adminListUsers).mockResolvedValue({
      users: [makeUser({ plan: "creator", subscription_status: "active", subscription_provider: "gifted" })],
      total: 1,
    });
    vi.mocked(api.adminUpdateSubscription).mockResolvedValue(
      makeUser({ plan: "free", subscription_status: "none", subscription_provider: "none" })
    );
    renderPage();
    await screen.findByText("target@example.com");
    const user = userEvent.setup();

    await user.click(screen.getByText("Manage subscription"));
    await user.selectOptions(screen.getByRole("combobox"), "free");
    await user.click(screen.getByRole("button", { name: "Revoke Gifted Subscription" }));
    expect(await screen.findByText(/back to Free/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Revoke Gifted Subscription" }));

    await waitFor(() => {
      expect(api.adminUpdateSubscription).toHaveBeenCalledWith("user-1", "free", undefined);
    });
  });

  it("passes a trimmed optional reason through to the API", async () => {
    vi.mocked(api.adminListUsers).mockResolvedValue({
      users: [makeUser({ plan: "free", subscription_status: "none", subscription_provider: "none" })],
      total: 1,
    });
    vi.mocked(api.adminUpdateSubscription).mockResolvedValue(makeUser({ subscription_provider: "gifted" }));
    renderPage();
    await screen.findByText("target@example.com");
    const user = userEvent.setup();

    await user.click(screen.getByText("Manage subscription"));
    await user.type(screen.getByPlaceholderText(/support case/i), "  internal partnership  ");
    await user.click(screen.getByRole("button", { name: "Grant Gifted Subscription" }));
    await user.click(screen.getByRole("button", { name: "Grant Gifted Subscription" }));

    await waitFor(() => {
      expect(api.adminUpdateSubscription).toHaveBeenCalledWith("user-1", "pro", "internal partnership");
    });
  });

  it("shows Gifted Subscription source and granted date in the user detail view", async () => {
    vi.mocked(api.adminListUsers).mockResolvedValue({
      users: [
        makeUser({
          plan: "creator",
          subscription_provider: "gifted",
          gifted_granted_at: "2026-09-13T00:00:00Z",
          gifted_granted_by_email: "owner@loady.cc",
        }),
      ],
      total: 1,
    });
    renderPage();
    await screen.findByText("target@example.com");
    const user = userEvent.setup();
    await user.click(screen.getByText("target@example.com"));

    expect(await screen.findByText("Gifted Subscription")).toBeInTheDocument();
    expect(screen.getByText("owner@loady.cc")).toBeInTheDocument();
  });

  it("shows the gifted controls and copy in Arabic", async () => {
    await i18n.changeLanguage("ar");
    vi.mocked(api.adminListUsers).mockResolvedValue({
      users: [makeUser({ plan: "free", subscription_status: "none", subscription_provider: "none" })],
      total: 1,
    });
    renderPage();
    await screen.findByText("target@example.com");
    const user = userEvent.setup();

    await user.click(screen.getByText("إدارة الاشتراك"));
    expect(await screen.findByText("هذا يمنح المستخدم صلاحية الوصول إلى Loady دون تحصيل أي رسوم.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "منح اشتراك مُهدى" })).toBeInTheDocument();
    await i18n.changeLanguage("en");
  });
});
