import type { ReactNode } from "react";
import { usePlatformUser } from "./PlatformAuthProvider";
import { useProductEntitlements } from "./useProductEntitlements";

export interface RequireCapabilityProps {
  /** Capability key to check, e.g. `"max_downloads"` or `"can_export"`. */
  capability: string;
  /** Only meaningful for an integer-valued capability - `-1` (unlimited)
   * always satisfies this. */
  atLeast?: number;
  /** Product to check against; defaults to `<PlatformAuthProvider productId>`. */
  productId?: string;
  children: ReactNode;
  /** Shown while identity or entitlements are still resolving. */
  loading?: ReactNode;
  /** Shown for every non-granted outcome: signed out, backend error,
   * product mismatch, or the capability simply being absent/false. This
   * package never distinguishes "denied" from "couldn't tell" in what it
   * renders - both must fail closed to the same safe fallback. */
  denied?: ReactNode;
}

/**
 * Fail-closed capability gate. `children` render only when the session is
 * `"authenticated"` AND the product entitlement resolved cleanly (status
 * `"ready"`) AND the capability check passes - any other combination
 * (loading, unauthenticated, network/backend error, wrong-product
 * mismatch, or an explicit `false`/missing capability) renders `denied`
 * (or `loading` while still in flight), never `children`.
 */
export function RequireCapability({ capability, atLeast, productId, children, loading = null, denied = null }: RequireCapabilityProps) {
  const { status: authStatus } = usePlatformUser();
  const { status: entStatus, hasCapability: check } = useProductEntitlements(productId);

  if (authStatus === "loading" || entStatus === "loading" || entStatus === "idle") {
    return <>{loading}</>;
  }
  if (authStatus !== "authenticated" || entStatus !== "ready") {
    return <>{denied}</>;
  }
  return check(capability, atLeast) ? <>{children}</> : <>{denied}</>;
}
