import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { PlatformAuthProvider, usePlatformUser } from "../PlatformAuthProvider";
import { useProductEntitlements } from "../useProductEntitlements";

function jsonResponse(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const AUTHENTICATED_USER = { sub: "usr_1", email: "a@example.test", email_verified: true };

function EntitlementProbe({ productId }: { productId?: string }) {
  const { status, entitlement, error } = useProductEntitlements(productId);
  return (
    <div>
      <span data-testid="ent-status">{status}</span>
      <span data-testid="ent-plan">{entitlement?.plan_slug ?? ""}</span>
      <span data-testid="ent-error">{error?.message ?? ""}</span>
    </div>
  );
}

describe("useProductEntitlements", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches the entitlement once the session is authenticated", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/entitlements")) {
        return Promise.resolve(jsonResponse(200, { product_id: "gamey", plan_slug: "gamer-plus", plan_name: "Gamer+", source: "paddle", capabilities: { max_saves: 50 } }));
      }
      return Promise.resolve(jsonResponse(200, { user: AUTHENTICATED_USER }));
    }));

    render(
      <PlatformAuthProvider productId="gamey">
        <EntitlementProbe />
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("ent-status").textContent).toBe("ready"));
    expect(screen.getByTestId("ent-plan").textContent).toBe("gamer-plus");
    vi.unstubAllGlobals();
  });

  it("never fetches entitlements for an unauthenticated session", async () => {
    const entitlementCalls: string[] = [];
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/entitlements")) entitlementCalls.push(url);
      if (url.includes("/entitlements")) return Promise.resolve(jsonResponse(200, {}));
      return Promise.resolve(jsonResponse(401));
    }));

    render(
      <PlatformAuthProvider productId="gamey">
        <EntitlementProbe />
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("ent-status").textContent).toBe("unauthenticated"));
    expect(entitlementCalls).toHaveLength(0);
    vi.unstubAllGlobals();
  });

  it("reports a mismatch when the backend returns a different product than requested", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/entitlements")) {
        return Promise.resolve(jsonResponse(200, { product_id: "filey", plan_slug: "business", plan_name: null, source: "paddle", capabilities: {} }));
      }
      return Promise.resolve(jsonResponse(200, { user: AUTHENTICATED_USER }));
    }));

    render(
      <PlatformAuthProvider>
        <EntitlementProbe productId="gamey" />
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("ent-status").textContent).toBe("mismatch"));
    expect(screen.getByTestId("ent-error").textContent).toMatch(/gamey/);
    expect(screen.getByTestId("ent-error").textContent).toMatch(/filey/);
    vi.unstubAllGlobals();
  });

  it("gracefully handles a session that expired between the auth check and the entitlement call, without throwing or looping", async () => {
    let sessionCalls = 0;
    let entitlementCalls = 0;
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/entitlements")) {
        entitlementCalls += 1;
        return Promise.resolve(jsonResponse(401));
      }
      sessionCalls += 1;
      // First session check says authenticated; the retry triggered by the
      // entitlement 401 (auth.refresh()) reveals it's actually gone now.
      return Promise.resolve(sessionCalls === 1 ? jsonResponse(200, { user: AUTHENTICATED_USER }) : jsonResponse(401));
    }));

    render(
      <PlatformAuthProvider productId="gamey">
        <EntitlementProbe />
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("ent-status").textContent).toBe("unauthenticated"));
    // Exactly one retry - not a loop - even though the backend keeps 401'ing.
    expect(entitlementCalls).toBe(1);
    expect(sessionCalls).toBe(2);
    vi.unstubAllGlobals();
  });

  it("throws a clear misconfiguration error when no productId is available anywhere", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(200, { user: AUTHENTICATED_USER }))));
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    function NoProductId() {
      useProductEntitlements();
      return null;
    }

    expect(() =>
      render(
        <PlatformAuthProvider>
          <NoProductId />
        </PlatformAuthProvider>
      )
    ).toThrow(/productId/);

    consoleError.mockRestore();
    vi.unstubAllGlobals();
  });

  it("surfaces a backend error distinctly from unauthenticated (fails closed)", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/entitlements")) return Promise.resolve(jsonResponse(500));
      return Promise.resolve(jsonResponse(200, { user: AUTHENTICATED_USER }));
    }));

    render(
      <PlatformAuthProvider productId="gamey">
        <EntitlementProbe />
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByTestId("ent-status").textContent).toBe("error"));
    vi.unstubAllGlobals();
  });
});

function AlsoUsePlatformUser() {
  usePlatformUser();
  return null;
}

describe("provider nesting", () => {
  it("re-throws for a second, unrelated hook usage outside any provider too", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<AlsoUsePlatformUser />)).toThrow(/PlatformAuthProvider/);
    consoleError.mockRestore();
  });
});
