import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { PlatformAuthProvider } from "../PlatformAuthProvider";
import { RequireAuth } from "../RequireAuth";
import { RequireCapability } from "../RequireCapability";

function jsonResponse(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const AUTHENTICATED_USER = { sub: "usr_1", email: "a@example.test", email_verified: true };

describe("RequireAuth", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders the loading node while the session check is in flight", async () => {
    let resolveFetch!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => (resolveFetch = resolve))));

    render(
      <PlatformAuthProvider>
        <RequireAuth loading={<span>loading-node</span>} fallback={<span>fallback-node</span>}>
          <span>secret</span>
        </RequireAuth>
      </PlatformAuthProvider>
    );

    expect(screen.getByText("loading-node")).toBeInTheDocument();
    resolveFetch(jsonResponse(401));
    await waitFor(() => expect(screen.getByText("fallback-node")).toBeInTheDocument());
    vi.unstubAllGlobals();
  });

  it("renders children only when authenticated", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(200, { user: AUTHENTICATED_USER }))));

    render(
      <PlatformAuthProvider>
        <RequireAuth fallback={<span>fallback-node</span>}>
          <span>secret</span>
        </RequireAuth>
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByText("secret")).toBeInTheDocument());
    expect(screen.queryByText("fallback-node")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("renders the fallback (not children) on a backend error - fails closed", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("down"))));

    render(
      <PlatformAuthProvider>
        <RequireAuth fallback={<span>fallback-node</span>}>
          <span>secret</span>
        </RequireAuth>
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByText("fallback-node")).toBeInTheDocument());
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});

describe("RequireCapability", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders children when the capability is present and truthy", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/entitlements")) return Promise.resolve(jsonResponse(200, { product_id: "gamey", plan_slug: "pro", plan_name: null, source: "paddle", capabilities: { ranked: true } }));
      return Promise.resolve(jsonResponse(200, { user: AUTHENTICATED_USER }));
    }));

    render(
      <PlatformAuthProvider productId="gamey">
        <RequireCapability capability="ranked" denied={<span>denied-node</span>}>
          <span>ranked-queue</span>
        </RequireCapability>
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByText("ranked-queue")).toBeInTheDocument());
    vi.unstubAllGlobals();
  });

  it("renders the denied node when the capability is absent - fails closed", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/entitlements")) return Promise.resolve(jsonResponse(200, { product_id: "gamey", plan_slug: "free", plan_name: null, source: null, capabilities: {} }));
      return Promise.resolve(jsonResponse(200, { user: AUTHENTICATED_USER }));
    }));

    render(
      <PlatformAuthProvider productId="gamey">
        <RequireCapability capability="ranked" denied={<span>denied-node</span>}>
          <span>ranked-queue</span>
        </RequireCapability>
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByText("denied-node")).toBeInTheDocument());
    expect(screen.queryByText("ranked-queue")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("fails closed (denied, not children) when signed out entirely", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(401))));

    render(
      <PlatformAuthProvider productId="gamey">
        <RequireCapability capability="ranked" denied={<span>denied-node</span>}>
          <span>ranked-queue</span>
        </RequireCapability>
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByText("denied-node")).toBeInTheDocument());
    vi.unstubAllGlobals();
  });

  it("fails closed on a backend error resolving entitlements", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/entitlements")) return Promise.resolve(jsonResponse(500));
      return Promise.resolve(jsonResponse(200, { user: AUTHENTICATED_USER }));
    }));

    render(
      <PlatformAuthProvider productId="gamey">
        <RequireCapability capability="ranked" denied={<span>denied-node</span>}>
          <span>ranked-queue</span>
        </RequireCapability>
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByText("denied-node")).toBeInTheDocument());
    expect(screen.queryByText("ranked-queue")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("honors an integer at_least threshold, including the -1 unlimited sentinel", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/entitlements")) return Promise.resolve(jsonResponse(200, { product_id: "gamey", plan_slug: "pro", plan_name: null, source: "paddle", capabilities: { max_saves: -1 } }));
      return Promise.resolve(jsonResponse(200, { user: AUTHENTICATED_USER }));
    }));

    render(
      <PlatformAuthProvider productId="gamey">
        <RequireCapability capability="max_saves" atLeast={999999} denied={<span>denied-node</span>}>
          <span>lots-of-saves</span>
        </RequireCapability>
      </PlatformAuthProvider>
    );

    await waitFor(() => expect(screen.getByText("lots-of-saves")).toBeInTheDocument());
    vi.unstubAllGlobals();
  });
});
