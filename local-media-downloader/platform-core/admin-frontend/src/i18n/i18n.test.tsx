import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Login from "../pages/Login";
import i18n from ".";
import { useAuth } from "../context/AuthContext";

vi.mock("../context/AuthContext", () => ({ useAuth: vi.fn() }));

describe("Grand Admin internationalization", () => {
  it("defaults to English with ltr direction", () => {
    expect(i18n.language).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
  });

  it("switches document direction to rtl for Arabic and renders Arabic copy", async () => {
    vi.mocked(useAuth).mockReturnValue({ user: null, loading: false, login: vi.fn(), logout: vi.fn(), refresh: vi.fn() });
    await i18n.changeLanguage("ar");
    expect(document.documentElement.dir).toBe("rtl");

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );
    expect(screen.getByText("الإدارة الكبرى")).toBeInTheDocument();

    await i18n.changeLanguage("en");
    expect(document.documentElement.dir).toBe("ltr");
  });
});
