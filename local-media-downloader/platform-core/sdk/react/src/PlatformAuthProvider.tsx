import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { AuthStatus, PlatformAuthContextValue, PlatformUser } from "./types";

export const PlatformAuthContext = createContext<PlatformAuthContextValue | null>(null);

export interface PlatformAuthProviderProps {
  /** Origin the product backend lives at. Omit for same-origin (the
   * common case: the product's frontend and backend share a domain, so
   * the httpOnly session cookie is sent automatically). */
  baseUrl?: string;
  /** Path prefix for the platform session/entitlement endpoints this
   * product's backend must expose. See README.md. Default "/api/platform". */
  basePath?: string;
  /** Default product_id for `useProductEntitlements`/`RequireCapability`
   * when they aren't given one explicitly. */
  productId?: string;
  children: ReactNode;
}

interface SessionResult {
  status: AuthStatus;
  user: PlatformUser | null;
  error: Error | null;
}

async function fetchSession(url: string): Promise<SessionResult> {
  let response: Response;
  try {
    response = await fetch(url, { credentials: "include", headers: { Accept: "application/json" } });
  } catch (err) {
    // Network failure / backend unreachable - distinct from a clean 401.
    // Never treated as "signed out," since that would be a lie about why
    // access was denied (mirrors the 503-not-403 rule the Python SDK's
    // `require_capability` dependency already applies).
    return { status: "error", user: null, error: err instanceof Error ? err : new Error(String(err)) };
  }
  if (response.status === 401) {
    return { status: "unauthenticated", user: null, error: null };
  }
  if (!response.ok) {
    return { status: "error", user: null, error: new Error(`Session check failed with status ${response.status}.`) };
  }
  try {
    const body = await response.json();
    const user = body?.user as PlatformUser | undefined;
    if (!user || typeof user.sub !== "string") {
      return { status: "error", user: null, error: new Error("Session response did not include a valid user.") };
    }
    return { status: "authenticated", user, error: null };
  } catch (err) {
    return { status: "error", user: null, error: err instanceof Error ? err : new Error(String(err)) };
  }
}

/**
 * Root provider for the platform integration layer. Talks ONLY to this
 * product's own backend (never to Platform Core directly) via the
 * documented contract in README.md - the backend is what holds the
 * httpOnly session cookie and resolves identity/entitlements against
 * Platform Core server-side using `platform_client`. This component never
 * reads or writes `localStorage`/`sessionStorage`; the only "state" it
 * holds is in React memory for the life of the tab.
 */
export function PlatformAuthProvider({ baseUrl = "", basePath = "/api/platform", productId, children }: PlatformAuthProviderProps) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<PlatformUser | null>(null);
  const [error, setError] = useState<Error | null>(null);

  // Single-flight guard: concurrent `refresh()` callers (the initial
  // mount effect, a manual retry button, and an entitlement hook noticing
  // a 401) all share one in-flight request instead of firing a fresh one
  // each, and none of them can start a *second* overlapping request.
  const inFlight = useRef<Promise<void> | null>(null);

  const applyResult = useCallback((result: SessionResult) => {
    setStatus(result.status);
    setUser(result.user);
    setError(result.error);
  }, []);

  const refresh = useCallback((): Promise<void> => {
    if (inFlight.current) return inFlight.current;
    const url = `${baseUrl}${basePath}/session`;
    const promise = fetchSession(url)
      .then(applyResult)
      .finally(() => {
        inFlight.current = null;
      });
    inFlight.current = promise;
    return promise;
  }, [baseUrl, basePath, applyResult]);

  const logout = useCallback(async (): Promise<void> => {
    try {
      await fetch(`${baseUrl}${basePath}/logout`, { method: "POST", credentials: "include" });
    } catch {
      // Best-effort: even if the network call fails, this tab must stop
      // believing it is signed in.
    }
    setStatus("unauthenticated");
    setUser(null);
    setError(null);
  }, [baseUrl, basePath]);

  useEffect(() => {
    void refresh();
    // Intentionally runs once per mount (and again only if baseUrl/basePath
    // identity changes) - this is the one and only automatic session
    // check; everything else is either a caller-triggered `refresh()` or
    // the single one-time retry `useProductEntitlements` does on a 401.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [baseUrl, basePath]);

  const value: PlatformAuthContextValue = { baseUrl, basePath, productId, status, user, error, refresh, logout };

  return <PlatformAuthContext.Provider value={value}>{children}</PlatformAuthContext.Provider>;
}

/** Access the current session. Must be called under a `<PlatformAuthProvider>`
 * - throws immediately otherwise rather than returning a misleadingly
 * "unauthenticated"-looking default, so a missing provider is caught in
 * development instead of silently denying every user. */
export function usePlatformUser(): PlatformAuthContextValue {
  const ctx = useContext(PlatformAuthContext);
  if (ctx === null) {
    throw new Error("usePlatformUser() was called outside a <PlatformAuthProvider>. Wrap your app (or this subtree) in one.");
  }
  return ctx;
}
