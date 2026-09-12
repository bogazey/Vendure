import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

/** Minimal fetch Response stand-in - only what request()/api.ts actually reads. */
function fakeResponse(status: number, body: unknown = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe("request() silent session-refresh on 401", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("retries once via /api/auth/refresh when a request 401s, and returns the retried result", async () => {
    fetchMock
      .mockResolvedValueOnce(fakeResponse(401, { message: "Sign in to continue." })) // GET /api/account
      .mockResolvedValueOnce(fakeResponse(200, { user: { id: "u1" } })) // POST /api/auth/refresh
      .mockResolvedValueOnce(fakeResponse(200, { user: { id: "u1", email: "a@example.com" } })); // retried GET /api/account

    const account = await api.getAccount();

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1][0])).toContain("/api/auth/refresh");
    expect((account as unknown as { user: { email: string } }).user.email).toBe("a@example.com");
  });

  it("does not retry, and surfaces the original 401, when the refresh itself fails", async () => {
    fetchMock
      .mockResolvedValueOnce(fakeResponse(401, { message: "Sign in to continue.", code: "AUTH_REQUIRED" }))
      .mockResolvedValueOnce(fakeResponse(401, { message: "expired" })); // refresh fails too

    await expect(api.getAccount()).rejects.toMatchObject({ status: 401 } satisfies Partial<ApiError>);
    expect(fetchMock).toHaveBeenCalledTimes(2); // original + one refresh attempt, no infinite loop
  });

  it("shares a single in-flight /api/auth/refresh call across concurrent 401s (no rotation race)", async () => {
    // Two different endpoints both 401 on their first call (simulating both
    // having been made right as the access token expired) - both must
    // collapse onto the SAME /api/auth/refresh call rather than each firing
    // its own, since the refresh endpoint rotates the token on every use.
    let refreshCalls = 0;
    let accountCallCount = 0;
    let downloadsCallCount = 0;
    fetchMock.mockImplementation(async (url: string) => {
      const href = String(url);
      if (href.includes("/api/auth/refresh")) {
        refreshCalls += 1;
        return fakeResponse(200, {});
      }
      if (href.includes("/api/account")) {
        accountCallCount += 1;
        return fakeResponse(accountCallCount === 1 ? 401 : 200, { ok: true });
      }
      if (href.includes("/api/downloads")) {
        downloadsCallCount += 1;
        return fakeResponse(downloadsCallCount === 1 ? 401 : 200, []);
      }
      return fakeResponse(404, {});
    });

    await Promise.all([api.getAccount(), api.listDownloads()]);

    expect(refreshCalls).toBe(1);
  });

  it("never attempts a refresh for a 401 from an /api/auth/* endpoint itself (no recursion)", async () => {
    fetchMock.mockResolvedValueOnce(fakeResponse(401, { message: "Incorrect email or password." }));

    await expect(api.login("a@example.com", "wrong")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1); // no /api/auth/refresh attempt
  });

  it("never calls refresh for a successful request", async () => {
    fetchMock.mockResolvedValueOnce(fakeResponse(200, { user: { id: "u1" } }));

    await api.getAccount();

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
