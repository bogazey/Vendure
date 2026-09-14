import type { ReactNode } from "react";
import { usePlatformUser } from "./PlatformAuthProvider";

export interface RequireAuthProps {
  children: ReactNode;
  /** Shown while the session check is in flight. */
  loading?: ReactNode;
  /** Shown when there is no session, or the backend could not be reached
   * (fails closed - both render this, never `children`). */
  fallback?: ReactNode;
}

/**
 * Router-agnostic gate: renders `children` only once the session is
 * confirmed `"authenticated"`. Everything else (`"loading"`,
 * `"unauthenticated"`, `"error"`) renders `loading`/`fallback` - this
 * package makes no assumption about routing, so redirecting to a sign-in
 * page is left to the host app (e.g. render a `<Navigate>` as `fallback`).
 */
export function RequireAuth({ children, loading = null, fallback = null }: RequireAuthProps) {
  const { status } = usePlatformUser();
  if (status === "loading") return <>{loading}</>;
  if (status === "authenticated") return <>{children}</>;
  return <>{fallback}</>;
}
