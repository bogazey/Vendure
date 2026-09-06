import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BillingManagement from "./BillingManagement";
import { api } from "../services/api";
import { openPaymentUpdate } from "../lib/paddle";
import i18n from "../i18n";

const state = vi.hoisted(() => ({ account: { subscription: { plan: "pro", status: "active", billing_period: "monthly", cancel_at_period_end: false } }, refresh: vi.fn() }));
vi.mock("../context/AuthContext", () => ({ useAuth: () => state }));
vi.mock("../services/api", () => ({ api: { manageSubscription: vi.fn(), updatePaymentMethod: vi.fn(), paymentHistory: vi.fn(), invoice: vi.fn() } }));
vi.mock("../lib/paddle", () => ({ openPaymentUpdate: vi.fn() }));
beforeEach(() => { vi.clearAllMocks(); state.account.subscription.cancel_at_period_end = false; });

describe("Billing management", () => {
  it.each([[false, "Cancel at period end", "cancel"], [true, "Resume subscription", "resume"]] as const)("confirms cancellation/resume %s", async (canceling, label, action) => {
    state.account.subscription.cancel_at_period_end = canceling;
    render(<BillingManagement />);
    await userEvent.click(screen.getByRole("button", { name: label }));
    expect(api.manageSubscription).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirm change" }));
    expect(api.manageSubscription).toHaveBeenCalledWith(action, "pro", "monthly");
    expect(await screen.findByText(/Request accepted/)).toBeInTheDocument();
  });
  it("changes plans through the backend", async () => {
    render(<BillingManagement />);
    await userEvent.selectOptions(screen.getAllByRole("combobox")[0], "creator");
    await userEvent.click(screen.getByRole("button", { name: "Change plan" }));
    expect(screen.getByText(/prorated charges/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Confirm change" }));
    expect(api.manageSubscription).toHaveBeenCalledWith("change-plan", "creator", "monthly");
  });
  it("opens only the payment overlay", async () => {
    const checkout = { transaction_id: "txn_owned", client_token: "test_public", environment: "sandbox" };
    vi.mocked(api.updatePaymentMethod).mockResolvedValue(checkout);
    render(<BillingManagement />);
    await userEvent.click(screen.getByRole("button", { name: "Update payment method" }));
    expect(openPaymentUpdate).toHaveBeenCalledWith(checkout, expect.any(Function));
  });
  it("shows payment history and a direct invoice link", async () => {
    vi.mocked(api.paymentHistory).mockResolvedValue({ items: [{ id: "txn_a", date: "2026-01-01", total: "499", currency: "USD", status: "completed", invoice_available: true }], next: null });
    vi.mocked(api.invoice).mockResolvedValue({ url: "https://example.com/invoice.pdf" });
    render(<BillingManagement />);
    await userEvent.click(screen.getByRole("button", { name: "View invoices / payment history" }));
    expect(screen.getByText("$4.99")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Get invoice" }));
    expect(screen.getByRole("link", { name: /Open invoice PDF/ })).toHaveAttribute("href", "https://example.com/invoice.pdf");
  });
  it("localizes provider failures in Arabic", async () => {
    await i18n.changeLanguage("ar");
    vi.mocked(api.updatePaymentMethod).mockRejectedValue(new Error("secret provider details"));
    render(<BillingManagement />);
    await userEvent.click(screen.getByRole("button", { name: "تحديث وسيلة الدفع" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("تعذر إكمال طلب الفوترة");
    expect(screen.queryByText("secret provider details")).not.toBeInTheDocument();
  });
});
