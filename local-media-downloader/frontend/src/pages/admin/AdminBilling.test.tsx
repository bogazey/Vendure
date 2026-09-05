import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import AdminBilling from "./AdminBilling";
import { api } from "../../services/api";
import type { AdminBillingEventOut } from "../../types/commercial";

vi.mock("../../services/api", () => ({
  api: { adminListBillingEvents: vi.fn() },
  ApiError: class ApiError extends Error {},
}));

function makeEvent(overrides: Partial<AdminBillingEventOut> = {}): AdminBillingEventOut {
  return {
    provider_event_id: "evt-1",
    event_type: "transaction.completed",
    processed_at: "2026-01-02T00:00:00Z",
    status: "processed",
    user_id: "user-1",
    user_email: "target@example.com",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminBilling />
    </MemoryRouter>
  );
}

describe("AdminBilling", () => {
  it("renders billing events with the user reference", async () => {
    vi.mocked(api.adminListBillingEvents).mockResolvedValue([makeEvent()]);
    renderPage();

    expect(await screen.findByText("transaction.completed")).toBeInTheDocument();
    expect(screen.getByText("target@example.com")).toBeInTheDocument();
  });

  it("shows a clearly failed outcome for a payment_failed event, separate from webhook status", async () => {
    vi.mocked(api.adminListBillingEvents).mockResolvedValue([
      makeEvent({ provider_event_id: "evt-2", event_type: "transaction.payment_failed", status: "processed" }),
    ]);
    renderPage();

    const outcomeCell = await screen.findByText("Payment failed");
    expect(outcomeCell.className).toMatch(/text-red-400/);
    // The webhook itself was processed successfully - that must not read as
    // a payment success signal (this was the bug: "processed" showed green).
    const webhookCell = await screen.findByText("Processed");
    expect(webhookCell.className).not.toMatch(/text-emerald-400/);
    expect(webhookCell.className).not.toMatch(/text-red-400/);
  });

  it("shows a green outcome for a completed transaction", async () => {
    vi.mocked(api.adminListBillingEvents).mockResolvedValue([makeEvent({ event_type: "transaction.completed" })]);
    renderPage();

    const outcomeCell = await screen.findByText("Completed");
    expect(outcomeCell.className).toMatch(/text-emerald-400/);
  });

  it("shows an empty state when there are no billing events", async () => {
    vi.mocked(api.adminListBillingEvents).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText(/no billing events yet/i)).toBeInTheDocument();
  });
});
