import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { PlatformAuthProvider, usePlatformUser } from "../PlatformAuthProvider";

function jsonResponse(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function Probe() {
  const { status, user, error } = usePlatformUser();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="email">{user?.email ?? ""}</span>
      <span data-testid="error">{error?.message ?? ""}</span>
    </div>
  );
}

describe("PlatformAuthProvider", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("reports loading before the session check resolves", async () => {
    let resolveFetch!: (r: Response) => void;
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => (resolveFetch = resolve)));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <PlatformAuthProvider>
        <Probe />
      </PlatformAuthProvider>
    );

    expect(screen.getByTestId("status").textContent).toBe("loading");
    resolveFetch(jsonResponse(401));
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
    vi.unstubAllGlobals();
  });

  it("resolves an authenticated user", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(200, { user: { sub: "usr_1", email: "a@example.test", email_verified: true } })))
    );

    render(
      <PlatformAuthProvider>
        <Probe />
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));
    expect(screen.getByTestId("email").textContent).toBe("a@example.test");
    vi.unstubAllGlobals();
  });

  it("resolves an unauthenticated (401) session cleanly, not as an error", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(401))));

    render(
      <PlatformAuthProvider>
        <Probe />
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
    vi.unstubAllGlobals();
  });

  it("reports a distinct error state on a backend/network failure - never treated as signed out", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network down"))));

    render(
      <PlatformAuthProvider>
        <Probe />
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("error"));
    expect(screen.getByTestId("error").textContent).toBe("network down");
    vi.unstubAllGlobals();
  });

  it("treats a non-401 non-ok response as an error, not a silent pass", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(500))));

    render(
      <PlatformAuthProvider>
        <Probe />
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("error"));
    vi.unstubAllGlobals();
  });

  it("never reads or writes localStorage or sessionStorage", async () => {
    const localSetItem = vi.spyOn(Storage.prototype, "setItem");
    const localGetItem = vi.spyOn(Storage.prototype, "getItem");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(200, { user: { sub: "usr_1", email: "a@example.test", email_verified: true } })))
    );

    render(
      <PlatformAuthProvider>
        <Probe />
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));
    expect(localSetItem).not.toHaveBeenCalled();
    expect(localGetItem).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
    localSetItem.mockRestore();
    localGetItem.mockRestore();
  });

  it("usePlatformUser() throws a clear error when used outside a provider", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow(/PlatformAuthProvider/);
    consoleError.mockRestore();
  });

  it("de-duplicates concurrent refresh() calls into a single request", async () => {
    let calls = 0;
    const fetchMock = vi.fn(() => {
      calls += 1;
      return Promise.resolve(jsonResponse(200, { user: { sub: "usr_1", email: "a@example.test", email_verified: true } }));
    });
    vi.stubGlobal("fetch", fetchMock);

    function DoubleRefresh() {
      const { refresh, status } = usePlatformUser();
      return (
        <div>
          <span data-testid="status">{status}</span>
          <button onClick={() => { void refresh(); void refresh(); }}>go</button>
        </div>
      );
    }

    render(
      <PlatformAuthProvider>
        <DoubleRefresh />
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));
    const callsAfterMount = calls;
    screen.getByText("go").click();
    await waitFor(() => expect(calls).toBeGreaterThan(callsAfterMount));
    // The two synchronous refresh() calls triggered by one click share a
    // single in-flight request - exactly one more call than before the click.
    expect(calls).toBe(callsAfterMount + 1);
    vi.unstubAllGlobals();
  });

  it("logout() clears local state even if the backend call fails, and never throws", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (typeof url === "string" && url.endsWith("/logout")) return Promise.reject(new Error("boom"));
      return Promise.resolve(jsonResponse(200, { user: { sub: "usr_1", email: "a@example.test", email_verified: true } }));
    }));

    function WithLogout() {
      const { status, logout } = usePlatformUser();
      return (
        <div>
          <span data-testid="status">{status}</span>
          <button onClick={() => void logout()}>out</button>
        </div>
      );
    }

    render(
      <PlatformAuthProvider>
        <WithLogout />
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));
    screen.getByText("out").click();
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
    vi.unstubAllGlobals();
  });
});
