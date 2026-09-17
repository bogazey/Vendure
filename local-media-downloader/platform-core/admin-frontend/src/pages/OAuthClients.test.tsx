import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import OAuthClients from "./OAuthClients";
import { oauthClientsApi } from "../services/api";

vi.mock("../services/api", async () => {
  const actual = await vi.importActual<typeof import("../services/api")>("../services/api");
  return {
    ...actual,
    oauthClientsApi: {
      ...actual.oauthClientsApi,
      list: vi.fn(),
      setActive: vi.fn(),
    },
  };
});

const LOADY_CLIENT = {
  client_id: "loady-client",
  name: "Loady Web",
  product_id: "loady",
  redirect_uris: ["https://loady.cc/callback"],
  post_logout_redirect_uris: ["https://loady.cc/after-logout"],
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const GAMEY_CLIENT = {
  client_id: "gamey-client",
  name: "Gamey Web",
  product_id: "gamey",
  redirect_uris: ["https://gamey.example/callback"],
  post_logout_redirect_uris: [],
  is_active: false,
  created_at: "2026-01-02T00:00:00Z",
};

describe("OAuthClients inventory page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(oauthClientsApi.list).mockResolvedValue([LOADY_CLIENT, GAMEY_CLIENT]);
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("lists every client returned by the backend, including cross-product rows", async () => {
    render(<OAuthClients />);
    expect(await screen.findByText("loady-client")).toBeInTheDocument();
    expect(screen.getByText("gamey-client")).toBeInTheDocument();
    expect(screen.getByText("loady")).toBeInTheDocument();
    expect(screen.getByText("gamey")).toBeInTheDocument();
  });

  it("never renders a secret or a hash", async () => {
    render(<OAuthClients />);
    await screen.findByText("loady-client");
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/hash/i)).not.toBeInTheDocument();
  });

  it("shows active/inactive status per client", async () => {
    render(<OAuthClients />);
    await screen.findByText("loady-client");
    const activeButtons = screen.getAllByRole("button", { name: "Disable" });
    const inactiveButtons = screen.getAllByRole("button", { name: "Enable" });
    expect(activeButtons).toHaveLength(1);
    expect(inactiveButtons).toHaveLength(1);
  });

  it("disabling an active client calls setActive(id, false) and reloads", async () => {
    vi.mocked(oauthClientsApi.setActive).mockResolvedValue({ client_id: "loady-client", is_active: false });
    render(<OAuthClients />);
    await screen.findByText("loady-client");

    fireEvent.click(screen.getByRole("button", { name: "Disable" }));

    await waitFor(() => {
      expect(oauthClientsApi.setActive).toHaveBeenCalledWith("loady-client", false);
    });
    expect(oauthClientsApi.list).toHaveBeenCalledTimes(2); // initial load + reload after toggle
  });

  it("re-enabling a disabled client calls setActive(id, true)", async () => {
    vi.mocked(oauthClientsApi.setActive).mockResolvedValue({ client_id: "gamey-client", is_active: true });
    render(<OAuthClients />);
    await screen.findByText("gamey-client");

    fireEvent.click(screen.getByRole("button", { name: "Enable" }));

    await waitFor(() => {
      expect(oauthClientsApi.setActive).toHaveBeenCalledWith("gamey-client", true);
    });
  });

  it("does not call setActive when the confirmation dialog is dismissed", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<OAuthClients />);
    await screen.findByText("loady-client");

    fireEvent.click(screen.getByRole("button", { name: "Disable" }));

    expect(oauthClientsApi.setActive).not.toHaveBeenCalled();
  });

  it("shows an empty state when there are no clients", async () => {
    vi.mocked(oauthClientsApi.list).mockResolvedValue([]);
    render(<OAuthClients />);
    expect(await screen.findByText("No OAuth clients registered yet.")).toBeInTheDocument();
  });
});
