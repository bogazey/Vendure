import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Overview from "./Overview";
import { api } from "../services/api";
import { useAuth } from "../context/AuthContext";

vi.mock("../services/api", async () => {
  const actual = await vi.importActual<typeof import("../services/api")>("../services/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      myMemberships: vi.fn(),
      myEntitlements: vi.fn(),
      listProducts: vi.fn(),
      mySecurityEvents: vi.fn(),
    },
  };
});
vi.mock("../context/AuthContext", () => ({ useAuth: vi.fn() }));

describe("Overview", () => {
  it("only shows products the user actually has a membership or entitlement in", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: "usr_1", email: "a@example.com", email_verified: true, status: "active", created_at: "2026-01-01T00:00:00Z", pending_new_email: null },
      loading: false,
      signup: vi.fn(),
      login: vi.fn(),
      logout: vi.fn(),
      refresh: vi.fn(),
    });
    vi.mocked(api.myMemberships).mockResolvedValue([
      { product_id: "loady", status: "active", first_seen_at: "2026-01-01T00:00:00Z", last_seen_at: "2026-01-02T00:00:00Z" },
    ]);
    vi.mocked(api.myEntitlements).mockResolvedValue([
      { product_id: "loady", plan_slug: "pro", plan_name: "Pro", source: "paddle", status: "active", starts_at: "2026-01-01T00:00:00Z", expires_at: null },
    ]);
    vi.mocked(api.listProducts).mockResolvedValue([
      { id: "loady", name: "Loady", domain: "loady.cc", status: "live", icon_ref: null },
      { id: "gamey", name: "Gamey", domain: "gamey.cc", status: "live", icon_ref: null },
    ]);
    vi.mocked(api.mySecurityEvents).mockResolvedValue([]);

    render(<Overview />);

    expect(await screen.findByText("Loady")).toBeInTheDocument();
    expect(screen.queryByText("Gamey")).not.toBeInTheDocument();
    expect(screen.getByText("Pro")).toBeInTheDocument();
  });
});
