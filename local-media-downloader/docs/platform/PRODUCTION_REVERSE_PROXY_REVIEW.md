# Reverse-Proxy Configuration Review (Mission 15, Phase 12)

## Routes required by Phase 12, checked against `nginx.production.conf.template` (206 lines, read in full)

| Route | Present before this mission | Present now |
|---|---|---|
| Central login / OIDC `authorize`/`callback` (`/oauth/*`) on `${RC_PLATFORM_AUTH_HOSTNAME}` | Yes | Yes (unchanged) |
| Platform API (`/api/*`) on `${RC_PLATFORM_AUTH_HOSTNAME}` | Yes | Yes (unchanged) |
| JWKS / discovery (`/.well-known/*`) on `${RC_PLATFORM_AUTH_HOSTNAME}` | Yes | Yes (unchanged) |
| `/health`, `/ready` passthroughs on `${RC_PLATFORM_AUTH_HOSTNAME}` | Yes | Yes (unchanged) |
| Account Portal (all paths) on `${RC_ACCOUNT_HOSTNAME}` | Yes, but... | Yes, and fixed (see finding below) |
| Grand Admin (all paths) on `${RC_ADMIN_HOSTNAME}` | Yes, but... | Yes, and fixed (see finding below) |
| Paddle webhook endpoint | Reachable today as a sub-path of `${RC_PLATFORM_AUTH_HOSTNAME}`'s `/api/*` block (`POST /api/v1/billing/webhooks/paddle`) — no separate route needed, confirmed by the existing regex already matching `^/(api/\|oauth/\|\.well-known/)` | Unchanged |
| Loady's existing routes preserved | Yes — the `loady.cc` server block is unchanged, condensed from `frontend/nginx.tls.conf` with an explicit comment keeping that file authoritative for Loady-only deployments | Unchanged |

## Genuine defect found and fixed: Account Portal and Grand Admin had no same-origin API route

**The finding**: both `platform-core/account-frontend/nginx.conf` and
`platform-core/admin-frontend/nginx.conf` contain this comment (identical
in both files):

> "the production reverse proxy in front of this container already routes
> `/api/*`, `/oauth/*`, `/.well-known/*`, `/health` and `/ready` to the
> backend instead, so nothing under those paths ever reaches here."

And `platform-core/.env.production.example` documents
`VITE_PLATFORM_API_BASE_URL=` (empty) as meaning "same-origin — the
combined edge routes `/api,/oauth,/.well-known` on each frontend's own
hostname to `platform-core-backend`." Both frontends' own API client code
confirms empty resolves to a same-origin relative fetch:

```ts
// account-frontend/src/services/api.ts and admin-frontend's equivalent
const API_BASE = import.meta.env.VITE_PLATFORM_API_BASE_URL ?? "http://localhost:8100";
```
(`??`, not `||` — an explicitly empty string is kept as `""`, meaning
`fetch(`${API_BASE}${path}`)` becomes a plain relative `fetch(path)`
against whatever hostname the page is loaded from.)

**But** the actual `${RC_ACCOUNT_HOSTNAME}` and `${RC_ADMIN_HOSTNAME}`
server blocks in `nginx.production.conf.template`, as they existed before
this mission, had only a single `location / { proxy_pass ...-frontend:80; }`
— **every** path, including `/api/*`, was sent straight to the static
frontend container. That container's own `nginx.conf` has no `/api/`
location of its own; its only non-asset rule is the SPA catch-all
`location / { try_files $uri /index.html; }`. The practical effect: with
the documented default configuration (`VITE_PLATFORM_API_BASE_URL` empty),
**every API call the Account Portal or Grand Admin frontend makes in
production would have silently received `index.html` (HTTP 200, wrong
content-type) instead of the JSON response it expects** — breaking login
status checks, session lists, entitlement views, and every Grand Admin
action, while showing no obvious server-side error (no 404, no 5xx — a 200
with the wrong body, which is a worse failure mode to diagnose than an
outright error).

**Why this was never caught**: nothing in any prior mission ever actually
ran the combined stack end-to-end — `MISSION_7_ARCHITECTURE_AUDIT.md` §5
explicitly recorded that a full build+run rehearsal of `compose.rc.yml`
was "deliberately not attempted" (resource-contention risk next to a
possibly-live personal Docker stack), and no environment used by any
mission since has had a Docker daemon available at all
(`FINAL_PREPRODUCTION_EVIDENCE_AUDIT.md` §1). The gap between the
*intended* design (documented consistently in three separate places: both
frontends' nginx comments and the env example) and the *actual* template
content was a pure static-review miss, invisible without either running
the stack or reading all three files side-by-side.

**The fix** (applied to `platform-core/reverse-proxy/nginx.production.conf.template`):
added the same `location ~ ^/(api/|oauth/|\.well-known/) { proxy_pass
http://platform-core-backend:8000; ... }` block — identical pattern to the
one already proven correct on `${RC_PLATFORM_AUTH_HOSTNAME}` — to both the
`${RC_ACCOUNT_HOSTNAME}` and `${RC_ADMIN_HOSTNAME}` server blocks, placed
before each one's catch-all `location /`. This makes the actual routing
match what every other file in the repo already assumed it did. No
application code changed; no new hostname, port, or upstream introduced —
only two `location` blocks added, reusing an existing, already-hardened
pattern.

**Why this is in-scope, not feature creep**: this is exactly the class of
fix the mission's own rule permits — "a genuine production-readiness
defect" discovered by this mission's review, fixed minimally, using a
pattern the codebase already established elsewhere rather than inventing
a new one.

## Validation performed

No Docker daemon is available in this environment, so the template cannot
be validated by actually starting the `reverse-proxy` container. Instead:

1. **Rendered** the template exactly as the official `nginx` image's
   `docker-entrypoint.d/20-envsubst-on-templates.sh` does — `envsubst`
   restricted to only the four `RC_*_HOSTNAME` variables (installed
   `gettext-base` locally for this; not a repo change), so nginx's own
   runtime `$host`/`$remote_addr`/etc. variables pass through untouched,
   matching the template's own documented assumption.
2. **Generated** a throwaway self-signed certificate (`openssl req -x509`,
   1-day validity, never used anywhere real) to satisfy `ssl_certificate`
   directives during the syntax check.
3. Added temporary `/etc/hosts` entries for `loady-backend`,
   `platform-core-backend`, `platform-core-account-frontend`,
   `platform-core-admin-frontend` (this sandbox only — not a repo or
   production change) so nginx's own static upstream-hostname resolution
   at config-load time would succeed, mimicking what Docker's embedded DNS
   provides for real inside a Compose network.
4. Ran `nginx -t` against the rendered config.

**Result: syntax OK**, with one caveat — this environment's installed
nginx is version 1.24.0, which does not support the standalone `http2 on;`
directive (introduced in nginx 1.25.1); the production image is pinned to
`nginx:1.27-alpine` (`platform-core/reverse-proxy/Dockerfile`), which does.
The `http2 on;` lines were temporarily removed for this local syntax check
only (not from the actual template) and are unaffected by this mission —
this is a **local validation-tool version gap**, not a defect in the
template itself; it is called out explicitly rather than silently working
around it without disclosure. Every other directive validated cleanly
against the exact, unmodified (post-fix) template content.

## Admin exposure review (Phase 12's specific concern)

Grand Admin (`${RC_ADMIN_HOSTNAME}`) is reachable from the public internet
through the edge exactly like Account Portal — there is no network-layer
restriction (no IP allowlist, no mTLS, no basic-auth in front of it). This
is a deliberate, pre-existing design choice (confirmed already true in
staging) rather than a new gap: access control is enforced at the
**application layer** by Grand Admin's own authentication, not the
reverse proxy. This mission does not add network-layer restriction
(IP allowlisting a Cloudflare-fronted origin is unreliable without
Cloudflare Access or a WAF rule anyway, and introducing either is exactly
the kind of infrastructure addition the No Feature Creep rule guards
against without a demonstrated need) — it is recorded here as an accepted
V1 posture, re-surfaced again in Phase 44's security review and Phase 54's
blocker classification rather than silently assumed fine without a paper
trail.
