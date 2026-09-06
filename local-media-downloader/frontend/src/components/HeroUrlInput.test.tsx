import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import HeroUrlInput from "./HeroUrlInput";

const navigateMock = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigateMock };
});

describe("HeroUrlInput", () => {
  it("sends a signed-out visitor straight to /dashboard to analyze - never to /signup", async () => {
    // Regression test for the bug this task fixes: a logged-out visitor
    // pasting a URL on the landing page must land on the downloader, not
    // be forced through account creation first.
    navigateMock.mockClear();
    render(
      <MemoryRouter>
        <HeroUrlInput />
      </MemoryRouter>
    );

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/paste a/i), "https://www.youtube.com/watch?v=abc123");
    await user.click(screen.getByRole("button", { name: /continue/i }));

    expect(navigateMock).toHaveBeenCalledWith("/dashboard", { state: { initialUrl: "https://www.youtube.com/watch?v=abc123" } });
    expect(navigateMock).not.toHaveBeenCalledWith("/signup", expect.anything());
  });

  it("shows a validation error instead of navigating for an invalid URL", async () => {
    navigateMock.mockClear();
    render(
      <MemoryRouter>
        <HeroUrlInput />
      </MemoryRouter>
    );

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/paste a/i), "not a url");
    await user.click(screen.getByRole("button", { name: /continue/i }));

    expect(navigateMock).not.toHaveBeenCalled();
  });
});
