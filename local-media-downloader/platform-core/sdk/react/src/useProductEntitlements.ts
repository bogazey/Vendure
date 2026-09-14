import { useCallback, useEffect, useRef, useState } from "react";
import { usePlatformUser } from "./PlatformAuthProvider";
import { hasCapability } from "./capabilities";
import type { Capabilities, EntitlementStatus, ProductEntitlement } from "./types";

export interface UseProductEntitlementsResult {
  status: EntitlementStatus;
  entitlement: ProductEntitlement | null;
  error: Error | null;
  refresh: () => Promise<void>;
  hasCapability: (key: string, atLeast?: number) => boolean;
}

async function fetchEntitlement(url: string): Promise<{ status: EntitlementStatus; entitlement: ProductEntitlement | null; error: Error | null; unauthenticated: boolean }> {
  let response: Response;
  try {
    response = await fetch(url, { credentials: "include", headers: { Accept: "application/json" } });
  } catch (err) {
    return { status: "error", entitlement: null, error: err instanceof Error ? err : new Error(String(err)), unauthenticated: false };
  }
  if (response.status === 401) {
    return { status: "unauthenticated", entitlement: null, error: null, unauthenticated: true };
  }
  if (!response.ok) {
    return { status: "error", entitlement: null, error: new Error(`Entitlement check failed with status ${response.status}.`), unauthenticated: false };
  }
  try {
    const body = (await response.json()) as ProductEntitlement;
    if (!body || typeof body.product_id !== "string") {
      return { status: "error", entitlement: null, error: new Error("Entitlement response did not include a product_id."), unauthenticated: false };
    }
    return { status: "ready", entitlement: body, error: null, unauthenticated: false };
  } catch (err) {
    return { status: "error", entitlement: null, error: err instanceof Error ? err : new Error(String(err)), unauthenticated: false };
  }
}

/**
 * Resolves the current user's entitlement for one product from that
 * product's own backend (`{basePath}/entitlements`), never from Platform
 * Core directly - see README.md for the contract. Requires a `productId`
 * either here or on `<PlatformAuthProvider productId="...">`; this
 * package never assumes any particular product, Loady included.
 *
 * Fails closed: while the surrounding session is `"loading"` this reports
 * `"loading"` (never a stale/optimistic previous value), and if the
 * session is anything other than cleanly `"authenticated"` this never
 * attempts the entitlement fetch at all.
 */
export function useProductEntitlements(productId?: string): UseProductEntitlementsResult {
  const auth = usePlatformUser();
  const effectiveProductId = productId ?? auth.productId;

  // Hooks below always run in the same order regardless of
  // `effectiveProductId` - the misconfiguration check is a plain `if`
  // AFTER every hook has been declared (see the end of this function),
  // never a conditional `throw` before a hook call.
  const [status, setStatus] = useState<EntitlementStatus>("idle");
  const [entitlement, setEntitlement] = useState<ProductEntitlement | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const inFlight = useRef<Promise<void> | null>(null);
  // Guards the automatic "session looked fine but this call 401'd" retry
  // to exactly one attempt per (productId, auth.user) pair, so a backend
  // that keeps returning 401 can never cause a retry loop.
  const retriedFor = useRef<string | null>(null);

  const load = useCallback((): Promise<void> => {
    if (!effectiveProductId) return Promise.resolve();
    if (inFlight.current) return inFlight.current;
    const url = `${auth.baseUrl}${auth.basePath}/entitlements?product_id=${encodeURIComponent(effectiveProductId)}`;
    const promise = fetchEntitlement(url)
      .then(async (result) => {
        if (result.unauthenticated) {
          const retryKey = `${effectiveProductId}:${auth.user?.sub ?? ""}`;
          if (retriedFor.current !== retryKey) {
            retriedFor.current = retryKey;
            // The session looked authenticated when this hook started but
            // the entitlement call itself got a 401 (e.g. the session
            // expired in the gap between the two requests, or was revoked
            // elsewhere) - re-check identity once so the UI can drop into
            // a correct "signed out" state instead of a confusing
            // authenticated-shell-with-no-entitlements.
            await auth.refresh();
          }
          setStatus("unauthenticated");
          setEntitlement(null);
          setError(null);
          return;
        }
        if (result.status === "ready" && result.entitlement && result.entitlement.product_id !== effectiveProductId) {
          setStatus("mismatch");
          setEntitlement(null);
          setError(
            new Error(`Requested entitlements for product "${effectiveProductId}" but the backend returned "${result.entitlement.product_id}".`)
          );
          return;
        }
        setStatus(result.status);
        setEntitlement(result.entitlement);
        setError(result.error);
      })
      .finally(() => {
        inFlight.current = null;
      });
    inFlight.current = promise;
    return promise;
  }, [auth, effectiveProductId]);

  useEffect(() => {
    if (!effectiveProductId) return;
    if (auth.status === "loading") {
      setStatus("loading");
      return;
    }
    if (auth.status === "unauthenticated") {
      setStatus("unauthenticated");
      setEntitlement(null);
      setError(null);
      return;
    }
    if (auth.status === "error") {
      // Fail closed: never guess at entitlements when identity itself
      // couldn't be resolved.
      setStatus("error");
      setEntitlement(null);
      setError(auth.error);
      return;
    }
    setStatus("loading");
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.status, auth.user?.sub, effectiveProductId]);

  const hasCap = useCallback((key: string, atLeast?: number) => hasCapability(entitlement?.capabilities as Capabilities | undefined, key, atLeast), [entitlement]);

  if (!effectiveProductId) {
    throw new Error(
      "useProductEntitlements() needs a productId - pass one as an argument or set productId on <PlatformAuthProvider>."
    );
  }

  return { status, entitlement, error, refresh: load, hasCapability: hasCap };
}
