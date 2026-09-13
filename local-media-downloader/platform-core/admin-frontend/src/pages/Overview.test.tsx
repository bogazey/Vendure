import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Overview from "./Overview";
import { api } from "../services/api";

vi.mock("../services/api", async () => {
  const actual = await vi.importActual<typeof import("../services/api")>("../services/api");
  return { ...actual, api: { ...actual.api, overview: vi.fn() } };
});

describe("Overview", () => {
  it("renders stat tiles from the overview endpoint", async () => {
    vi.mocked(api.overview).mockResolvedValue({
      total_users: 12,
      active_users: 10,
      total_products: 3,
      paid_entitlements: 4,
      gifted_entitlements: 2,
      revenue_available: false,
      revenue_note: "No real payment processor is wired into Platform Core in V1 - revenue is intentionally not fabricated.",
    });
    render(<Overview />);

    expect(await screen.findByTestId("tile-total_users")).toHaveTextContent("12");
    expect(screen.getByTestId("tile-gifted_entitlements")).toHaveTextContent("2");
    expect(screen.getByText(/not fabricated/i)).toBeInTheDocument();
  });

  it("shows a forbidden message for a non-admin caller", async () => {
    const { ApiError } = await vi.importActual<typeof import("../services/api")>("../services/api");
    vi.mocked(api.overview).mockRejectedValue(new ApiError("FORBIDDEN", "Grand Admin access required.", 403));
    render(<Overview />);

    expect(await screen.findByText("Access denied")).toBeInTheDocument();
  });
});
