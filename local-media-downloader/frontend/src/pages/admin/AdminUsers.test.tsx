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
