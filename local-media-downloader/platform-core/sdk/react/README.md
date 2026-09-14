# @platform-core/react-client

The reusable browser-side integration layer for a product joining the
Platform Core ecosystem. Pairs with the Python `platform_client` SDK
(`platform-core/sdk/python`), which does the equivalent job on a product's
*backend*.

## Design: talk to your own backend, never to Platform Core directly

This package never calls Platform Core's API from the browser. Instead it
calls **this product's own backend**, at a small, documented JSON contract.
The product's backend is what:

- holds the httpOnly session cookie (this package never sees a token),
- performed the real OIDC/PKCE exchange with Platform Core
  (`platform_client.PlatformClient`),
- resolves entitlements/capabilities server-side via `platform_client`'s
  service-token + effective-entitlement calls.

This is exactly the same shape as `platform-core/admin-frontend` and
`platform-core/account-frontend`'s own `AuthContext` (cookie + `/me`
endpoint) - this package generalizes that pattern so a new product's
frontend never has to hand-roll it again, and never has to hardcode which
product it is.

## Required backend contract

A product backend that wants to use this package must expose, under some
path prefix (`basePath`, default `/api/platform`), same-origin to its own
frontend, with the session cookie already `httpOnly`/`SameSite`:

### `GET {basePath}/session`

- `200 { "user": { "sub": string, "email": string, "email_verified": boolean } }`
  when the request's session cookie identifies a signed-in user.
- `401` (body ignored) when there is no session or it is invalid/expired.
- Anything else is treated as `"error"` (backend reachable but broken),
  which is intentionally distinct from `"unauthenticated"` - a broken
  backend must never be indistinguishable from "you're signed out."

### `GET {basePath}/entitlements?product_id=<id>`

- `200` with:
  ```json
  {
    "product_id": "gamey",
    "plan_slug": "gamer-plus",
    "plan_name": "Gamer+",
    "source": "paddle",
    "capabilities": { "max_saves": 50, "ranked_matchmaking": true }
  }
  ```
- `401` when there is no session.
- The `product_id` in the response is checked against what was requested -
  a mismatch is surfaced as a distinct `"mismatch"` status rather than
  silently rendering the wrong product's entitlement.

A minimal FastAPI implementation of both routes, built on
`platform_client.fastapi_ext`, is provided by the Python SDK - see
`platform_client.fastapi_ext.build_platform_router`.

### `POST {basePath}/logout` (optional)

Called by `usePlatformUser().logout()`. If your backend doesn't implement
it, the call fails silently and local React state is cleared anyway - this
tab stops believing it is signed in either way.

## Usage

```tsx
import { PlatformAuthProvider, usePlatformUser, useProductEntitlements, RequireAuth, RequireCapability } from "@platform-core/react-client";

function App() {
  return (
    <PlatformAuthProvider productId="gamey">
      <RequireAuth fallback={<SignInPrompt />} loading={<Spinner />}>
        <Dashboard />
      </RequireAuth>
    </PlatformAuthProvider>
  );
}

function Dashboard() {
  const { user, logout } = usePlatformUser();
  const { entitlement, hasCapability } = useProductEntitlements();
  return (
    <div>
      <p>Signed in as {user!.email}</p>
      <p>Plan: {entitlement?.plan_name ?? "Free"}</p>
      <RequireCapability capability="ranked_matchmaking" denied={<UpgradePrompt />}>
        <RankedQueueButton />
      </RequireCapability>
      <button onClick={logout}>Sign out</button>
    </div>
  );
}
```

## Guarantees

- **No token persistence.** Never reads or writes `localStorage` or
  `sessionStorage`. Every request uses `credentials: "include"` against
  the backend's own httpOnly cookie.
- **Fails closed.** `RequireCapability` denies on loading-that-hasn't-
  finished, backend errors, and product mismatches - the same as an
  outright `false` capability. It never renders `children` on anything
  short of a clean, confirmed "yes."
- **No hardcoded product.** `productId` is always supplied by the
  consuming app - via the provider or per-hook-call.
- **Single-flight, no refresh loops.** Concurrent `refresh()` calls (or an
  entitlement fetch's own automatic one-time re-check after a 401) share
  one in-flight request; the automatic retry only ever fires once per
  (product, user) pair, never repeatedly against a backend that keeps
  saying no.
