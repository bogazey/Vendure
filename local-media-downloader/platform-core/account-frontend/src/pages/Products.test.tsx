import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Products from "./Products";
import { api } from "../services/api";

vi.mock("../services/api", async () => {
  const actual = await vi.importActual<typeof import("../services/api")>("../services/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      listProducts: vi.fn(),
      myMemberships: vi.fn(),
      myEntitlements: vi.fn(),
    },
  };
});

describe("Products", () => {
  it("shows a product the user only has an entitlement for, not yet a membership in", async () => {
    // Regression: a gifted/paid/promo user who has never signed into the
    // product's own SSO flow yet still has real product access - the page
    // must not tell them they "haven't joined any products yet" while
    // Overview and Billing both correctly show the same product.
    vi.mocked(api.myMemberships).mockResolvedValue([]);
    vi.mocked(api.myEntitlements).mockResolvedValue([
      { product_id: "gamey", plan_slug: "gamer-plus", plan_name: "Gamer+", source: "gifted", status: "active", starts_at: "2026-01-01T00:00:00Z", expires_at: null },
    ]);
    vi.mocked(api.listProducts).mockResolvedValue([
      { id: "gamey", name: "Gamey", domain: "gamey.cc", status: "planned", icon_ref: null },
    ]);

    render(<Products />);

    expect(await screen.findByText("Gamey")).toBeInTheDocument();
    expect(screen.getByText("Gamer+")).toBeInTheDocument();
    expect(screen.queryByText("You haven't joined any products yet.")).not.toBeInTheDocument();
  });

  it("does not show a product whose only entitlement has been revoked", async () => {
    // Regression: /me/entitlements returns full history (revoked/expired
    // included) since admin views need it - the account portal must
    // filter to active entitlements or a revoked gift keeps showing as
    // if the user still has it.
    vi.mocked(api.myMemberships).mockResolvedValue([]);
    vi.mocked(api.myEntitlements).mockResolvedValue([
      { product_id: "gamey", plan_slug: "gamer-plus", plan_name: "Gamer+", source: "gifted", status: "revoked", starts_at: "2026-01-01T00:00:00Z", expires_at: null },
    ]);
    vi.mocked(api.listProducts).mockResolvedValue([
      { id: "gamey", name: "Gamey", domain: "gamey.cc", status: "planned", icon_ref: null },
    ]);

    render(<Products />);

    expect(await screen.findByText("You haven't joined any products yet.")).toBeInTheDocument();
    expect(screen.queryByText("Gamey")).not.toBeInTheDocument();
  });

  it("does not offer a product to Discover if the user already has an entitlement for it", async () => {
    vi.mocked(api.myMemberships).mockResolvedValue([]);
    vi.mocked(api.myEntitlements).mockResolvedValue([
      { product_id: "gamey", plan_slug: "gamer-plus", plan_name: "Gamer+", source: "gifted", status: "active", starts_at: "2026-01-01T00:00:00Z", expires_at: null },
    ]);
    vi.mocked(api.listProducts).mockResolvedValue([
      { id: "gamey", name: "Gamey", domain: "gamey.cc", status: "live", icon_ref: null },
    ]);

    render(<Products />);

    await screen.findByText("Gamer+");
    expect(screen.queryByText("Learn more")).not.toBeInTheDocument();
  });
});
