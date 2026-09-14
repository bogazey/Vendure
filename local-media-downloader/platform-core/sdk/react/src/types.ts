/** The verified identity behind the product backend's own session cookie -
 * `sub` is the immutable global_user_id, never the email (mirrors
 * `platform_client.PlatformUser` on the Python side). */
export interface PlatformUser {
  sub: string;
  email: string;
  email_verified: boolean;
}

/** Lifecycle of the central identity check. `"error"` means the backend
 * could not be reached or returned something unexpected - distinct from
 * `"unauthenticated"` (a clean 401) so callers can fail closed on both
 * without confusing "no session" with "don't know." */
export type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "error";

/** A capability value as returned by the effective-entitlement resolver:
 * boolean gates, integer limits (`-1` means unlimited), or a string/enum
 * tier. Mirrors the shape `platform_client.PlatformClient.has_capability`
 * already expects on the Python side. */
export type CapabilityValue = boolean | number | string;
export type Capabilities = Record<string, CapabilityValue>;

/** One product's resolved entitlement for the current user, as returned by
 * the product backend's `{basePath}/entitlements` endpoint. */
export interface ProductEntitlement {
  product_id: string;
  plan_slug: string | null;
  plan_name: string | null;
  source: string | null;
  capabilities: Capabilities;
}

export type EntitlementStatus = "idle" | "loading" | "ready" | "unauthenticated" | "error" | "mismatch";

export interface PlatformAuthContextValue {
  /** Origin the product backend's API lives at. Empty string means
   * same-origin (the common case - the product's own frontend and backend
   * are served from the same domain). */
  baseUrl: string;
  /** Path prefix under `baseUrl` the product backend mounts the platform
   * session/entitlement endpoints at. See README.md for the contract. */
  basePath: string;
  /** Default product_id used by `useProductEntitlements`/`RequireCapability`
   * when no explicit `productId` is passed - lets a product configure this
   * once instead of repeating its own id at every call site. Never
   * hardcoded by this package itself. */
  productId?: string;
  status: AuthStatus;
  user: PlatformUser | null;
  error: Error | null;
  /** Re-checks the session against the backend. Safe to call from
   * multiple places concurrently - calls in flight share one request. */
  refresh: () => Promise<void>;
  /** Calls `{basePath}/logout` (if the backend implements it) and clears
   * local state regardless of whether that call succeeds, since the goal
   * is this tab no longer believing it is signed in. */
  logout: () => Promise<void>;
}
