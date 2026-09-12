import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import Login from "./Login";
import i18n from "../../i18n";
import { useAuth } from "../../context/AuthContext";

vi.mock("../../context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Login />
    </MemoryRouter>
  );
}

describe("Login", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({
      account: null, loading: false, refresh: vi.fn(),
      login: vi.fn().mockResolvedValue(undefined),
      signup: vi.fn(), logout: vi.fn(),
    });
  });

  it("renders the Keep me logged in checkbox, unchecked by default", () => {
    renderLogin();
    const checkbox = screen.getByRole("checkbox", { name: "Keep me logged in" });
    expect(checkbox).toBeInTheDocument();
    expect(checkbox).not.toBeChecked();
  });

  it("renders the checkbox label in Arabic", async () => {
    await i18n.changeLanguage("ar");
    renderLogin();
    expect(screen.getByText("إبقائي مسجلاً للدخول")).toBeInTheDocument();
    await i18n.changeLanguage("en");
  });

  it("submits with rememberMe=false when the checkbox is left unchecked", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({
      account: null, loading: false, refresh: vi.fn(), login, signup: vi.fn(), logout: vi.fn(),
    });
    renderLogin();

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "a@example.com");
    await user.type(screen.getByLabelText("Password", { exact: false }), "correcthorse9!");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(login).toHaveBeenCalledWith("a@example.com", "correcthorse9!", false);
  });

  it("submits with rememberMe=true when the checkbox is checked", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({
      account: null, loading: false, refresh: vi.fn(), login, signup: vi.fn(), logout: vi.fn(),
    });
    renderLogin();

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "a@example.com");
    await user.type(screen.getByLabelText("Password", { exact: false }), "correcthorse9!");
    await user.click(screen.getByRole("checkbox", { name: "Keep me logged in" }));
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(login).toHaveBeenCalledWith("a@example.com", "correcthorse9!", true);
  });
});
