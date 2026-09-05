import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import AdminAds from "./AdminAds";
import i18n from "../../i18n";
import { api } from "../../services/api";
import type { AdminAdPlacementOut } from "../../types/commercial";

vi.mock("../../services/api", () => ({
  api: { adminListAdPlacements: vi.fn(), adminUpdateAdPlacement: vi.fn() },
  ApiError: class ApiError extends Error {},
}));

function makePlacement(overrides: Partial<AdminAdPlacementOut> = {}): AdminAdPlacementOut {
  return {
    id: "LANDING_DOWNLOADER",
    description: "Below the URL input on the marketing landing page downloader.",
    enabled: false,
    provider: null,
    public_slot_id: null,
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminAds />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.mocked(api.adminListAdPlacements).mockResolvedValue([makePlacement()]);
});

describe("AdminAds", () => {
  it("lists placements with their id, description, and disabled state", async () => {
    renderPage();
    expect(await screen.findByText("Landing downloader")).toBeInTheDocument();
    expect(screen.getByText("LANDING_DOWNLOADER")).toBeInTheDocument();
    expect(screen.getByText(/below the url input/i)).toBeInTheDocument();
    expect(screen.getByText("Disabled")).toBeInTheDocument();
  });

  it("enables a placement", async () => {
    vi.mocked(api.adminUpdateAdPlacement).mockResolvedValue(makePlacement({ enabled: true }));
    renderPage();
    await screen.findByText("Landing downloader");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Enable" }));

    expect(api.adminUpdateAdPlacement).toHaveBeenCalledWith("LANDING_DOWNLOADER", { enabled: true });
    expect(await screen.findByRole("button", { name: "Disable" })).toBeInTheDocument();
  });

  it("configures a provider and slot id through the dialog", async () => {
    vi.mocked(api.adminUpdateAdPlacement).mockResolvedValue(
      makePlacement({ provider: "google_adsense", public_slot_id: "slot-1" })
    );
    renderPage();
    await screen.findByText("Landing downloader");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Configure" }));
    await user.type(await screen.findByPlaceholderText(/google_adsense/i), "google_adsense");
    await user.type(screen.getByPlaceholderText(/slot-1234/i), "slot-1");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(api.adminUpdateAdPlacement).toHaveBeenCalledWith("LANDING_DOWNLOADER", {
      provider: "google_adsense",
      public_slot_id: "slot-1",
    });
  });

  it("renders in Arabic with translated placement labels", async () => {
    await i18n.changeLanguage("ar");
    renderPage();
    expect(await screen.findByText("أداة التنزيل في الصفحة الرئيسية")).toBeInTheDocument();
    expect(screen.getByText("معطّل")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "تفعيل" })).toBeInTheDocument();
    // The technical identifier itself stays untranslated/LTR.
    expect(screen.getByText("LANDING_DOWNLOADER")).toHaveAttribute("dir", "ltr");
  });
});
