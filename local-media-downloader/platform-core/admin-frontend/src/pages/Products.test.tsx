import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import Products from "./Products";
import { api } from "../services/api";

vi.mock("../services/api", async () => {
  const actual = await vi.importActual<typeof import("../services/api")>("../services/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      listProducts: vi.fn(),
      onboardProduct: vi.fn(),
    },
  };
});

function fillOnboardingForm() {
  fireEvent.change(screen.getByPlaceholderText("filey"), { target: { value: "filey" } });
  fireEvent.change(screen.getByPlaceholderText("Filey"), { target: { value: "Filey" } });
  fireEvent.change(screen.getByPlaceholderText("filey.cc"), { target: { value: "filey.cc" } });
  fireEvent.change(screen.getByPlaceholderText("filey-client"), { target: { value: "filey-client" } });
  fireEvent.change(screen.getByPlaceholderText("Filey Web Client"), { target: { value: "Filey Web Client" } });
  fireEvent.change(screen.getByPlaceholderText("https://filey.cc/auth/callback"), { target: { value: "https://filey.cc/auth/callback" } });
}

describe("Products onboarding", () => {
  beforeEach(() => {
    vi.mocked(api.listProducts).mockResolvedValue([]);
  });

  it("reveals the client secret exactly once, with the required warning, on success", async () => {
    vi.mocked(api.onboardProduct).mockResolvedValue({
      product: { id: "filey", name: "Filey", domain: "filey.cc", status: "planned", icon_ref: null, description: null, is_discoverable: true, created_at: "2026-01-01T00:00:00Z" },
      client_id: "filey-client",
      client_secret: "super-secret-plaintext-value",
    });

    render(<Products />);
    await screen.findByRole("button", { name: "Add product" });
    fillOnboardingForm();
    fireEvent.click(screen.getByRole("button", { name: "Add product" }));

    expect(await screen.findByText("Product onboarded")).toBeInTheDocument();
    expect(screen.getByText(/will not be shown again/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue("super-secret-plaintext-value")).toBeInTheDocument();
  });

  it("shows a clear inline error, not a crash, when onboarding is rejected (e.g. not a super admin)", async () => {
    const { ApiError } = await vi.importActual<typeof import("../services/api")>("../services/api");
    vi.mocked(api.onboardProduct).mockRejectedValue(new ApiError("FORBIDDEN", "Only a super admin may onboard a product.", 403));

    render(<Products />);
    await screen.findByRole("button", { name: "Add product" });
    fillOnboardingForm();
    fireEvent.click(screen.getByRole("button", { name: "Add product" }));

    expect(await screen.findByText("Only a super admin may onboard a product.")).toBeInTheDocument();
    expect(screen.queryByText("Product onboarded")).not.toBeInTheDocument();
  });

  it("never writes the onboarded secret to localStorage or sessionStorage", async () => {
    const localSetItem = vi.spyOn(Storage.prototype, "setItem");
    vi.mocked(api.onboardProduct).mockResolvedValue({
      product: { id: "filey", name: "Filey", domain: "filey.cc", status: "planned", icon_ref: null, description: null, is_discoverable: true, created_at: "2026-01-01T00:00:00Z" },
      client_id: "filey-client",
      client_secret: "super-secret-plaintext-value",
    });

    render(<Products />);
    await screen.findByRole("button", { name: "Add product" });
    fillOnboardingForm();
    fireEvent.click(screen.getByRole("button", { name: "Add product" }));
    await screen.findByText("Product onboarded");

    expect(localSetItem).not.toHaveBeenCalledWith(expect.anything(), expect.stringContaining("super-secret-plaintext-value"));
    localSetItem.mockRestore();
  });

  it("auto-fills the client id from a multi-character product id typed one keystroke at a time", async () => {
    // Regression: the auto-default effect compared the reconstructed
    // previous default against the CURRENT id on every render, which only
    // matched for a single-character id - typing "sample-future-2"
    // normally (one keystroke per render) left the client id stuck at
    // "s-client" after the first character.
    render(<Products />);
    await waitFor(() => expect(api.listProducts).toHaveBeenCalled());
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("filey"), "sample-future-2");

    expect(screen.getByPlaceholderText("filey-client")).toHaveValue("sample-future-2-client");
  });

  it("stops auto-filling the client id once the admin edits it directly", async () => {
    render(<Products />);
    await waitFor(() => expect(api.listProducts).toHaveBeenCalled());
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText("filey"), "sample-future-2");
    await user.clear(screen.getByPlaceholderText("filey-client"));
    await user.type(screen.getByPlaceholderText("filey-client"), "custom-client-id");
    await user.type(screen.getByPlaceholderText("filey"), "-more");

    expect(screen.getByPlaceholderText("filey-client")).toHaveValue("custom-client-id");
  });

  it("disables submit until the required fields are filled", async () => {
    render(<Products />);
    await waitFor(() => expect(api.listProducts).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Add product" })).toBeDisabled();
    fillOnboardingForm();
    expect(screen.getByRole("button", { name: "Add product" })).not.toBeDisabled();
  });
});
