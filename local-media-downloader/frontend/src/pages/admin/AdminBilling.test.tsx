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

  it("visually distinguishes failed payment events", async () => {
    vi.mocked(api.adminListBillingEvents).mockResolvedValue([
      makeEvent({ provider_event_id: "evt-2", event_type: "transaction.payment_failed", status: "failed" }),
    ]);
    renderPage();

    const eventCell = await screen.findByText("transaction.payment_failed");
    expect(eventCell.className).toMatch(/text-red-400/);
  });

  it("shows an empty state when there are no billing events", async () => {
    vi.mocked(api.adminListBillingEvents).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText(/no billing events yet/i)).toBeInTheDocument();
  });
});
