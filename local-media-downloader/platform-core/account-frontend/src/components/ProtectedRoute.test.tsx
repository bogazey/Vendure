import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import ProtectedRoute from "./ProtectedRoute";
import { useAuth } from "../context/AuthContext";

vi.mock("../context/AuthContext", () => ({ useAuth: vi.fn() }));

function renderWithAuth(authValue: Partial<ReturnType<typeof useAuth>>) {
  vi.mocked(useAuth).mockReturnValue({
    user: null,
    loading: false,
    signup: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
    ...authValue,
  });
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route path="/" element={<ProtectedRoute><div>Protected content</div></ProtectedRoute>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ProtectedRoute", () => {
  it("redirects to /login when signed out", () => {
    renderWithAuth({ user: null, loading: false });
    expect(screen.getByText("Login page")).toBeInTheDocument();
  });

  it("renders children when signed in", () => {
    renderWithAuth({
      user: { id: "usr_1", email: "a@example.com", email_verified: true, status: "active", created_at: "2026-01-01T00:00:00Z", pending_new_email: null },
      loading: false,
    });
    expect(screen.getByText("Protected content")).toBeInTheDocument();
  });

  it("renders nothing while loading", () => {
    const { container } = renderWithAuth({ user: null, loading: true });
    expect(container.textContent).toBe("");
  });
});
