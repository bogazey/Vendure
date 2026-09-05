import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Header from "../components/Header";
import HeroUrlInput from "../components/HeroUrlInput";
import Sidebar from "../components/Sidebar";
import i18n, { LANGUAGE_STORAGE_KEY } from ".";
import { useAuth } from "../context/AuthContext";

vi.mock("../context/AuthContext", () => ({ useAuth: vi.fn() }));

const signedOut = { account: null, loading: false, refresh: vi.fn(), login: vi.fn(), signup: vi.fn(), logout: vi.fn() };

describe("English and Arabic internationalization", () => {
  it("defaults to English and switches document direction and navigation to Arabic", async () => {
    vi.mocked(useAuth).mockReturnValue(signedOut);
    localStorage.removeItem(LANGUAGE_STORAGE_KEY);
    await i18n.changeLanguage("en");
    render(<MemoryRouter><Header health={null} healthError={false} /></MemoryRouter>);

    expect(document.documentElement).toHaveAttribute("lang", "en");
    expect(document.documentElement).toHaveAttribute("dir", "ltr");
    expect(screen.getAllByText("Features").length).toBeGreaterThan(0);

    await userEvent.click(screen.getAllByRole("button", { name: "العربية" })[0]);
    expect(document.documentElement).toHaveAttribute("lang", "ar");
    expect(document.documentElement).toHaveAttribute("dir", "rtl");
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("ar");
    expect(screen.getAllByText("المزايا").length).toBeGreaterThan(0);
    expect(screen.getAllByText("الأسعار").length).toBeGreaterThan(0);
  });

  it("switches back to English and keeps URL input LTR in Arabic", async () => {
    vi.mocked(useAuth).mockReturnValue(signedOut);
    await i18n.changeLanguage("ar");
    const { rerender } = render(<MemoryRouter><HeroUrlInput /></MemoryRouter>);
    expect(screen.getByRole("textbox")).toHaveAttribute("dir", "ltr");

    await i18n.changeLanguage("en");
    rerender(<MemoryRouter><Header health={null} healthError={false} /></MemoryRouter>);
    expect(document.documentElement).toHaveAttribute("lang", "en");
    expect(document.documentElement).toHaveAttribute("dir", "ltr");
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("en");
  });

  it("translates authenticated application navigation", async () => {
    vi.mocked(useAuth).mockReturnValue({
      account: { user: { role: "user" } },
      logout: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>);
    await i18n.changeLanguage("ar");
    render(<MemoryRouter><Sidebar /></MemoryRouter>);

    expect(screen.getByText("تنزيلاتي")).toBeInTheDocument();
    expect(screen.getByText("الإعدادات")).toBeInTheDocument();
    expect(screen.getByText("الفوترة")).toBeInTheDocument();
  });
});
