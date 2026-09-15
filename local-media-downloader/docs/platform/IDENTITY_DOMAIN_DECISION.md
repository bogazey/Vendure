# Identity Domain Decision (Mission 15, Phase 4)

**Status: awaiting the business owner's confirmation. Not a code or
infrastructure blocker** — every part of the architecture (`compose.rc.yml`,
`nginx.production.conf.template`, `platform-core/.env.production.example`)
already takes every hostname as a variable, so this decision changes zero
lines of application code or Compose structure, only the values of four
environment variables (`RC_LOADY_HOSTNAME`, `RC_PLATFORM_AUTH_HOSTNAME`,
`RC_ACCOUNT_HOSTNAME`, `RC_ADMIN_HOSTNAME`) and the two build-time
`VITE_PLATFORM_API_BASE_URL`/`PLATFORM_AUTH_BASE_URL`/`PLATFORM_API_BASE_URL`
settings. This mission does not create any DNS record or Cloudflare zone —
see `CLOUDFLARE_CUTOVER_PLAN.md` for what happens once this decision is made.

## RECOMMENDED INITIAL CONFIGURATION

Subdomains of the existing `loady.cc` zone:

| Surface | Hostname |
|---|---|
| Loady (unchanged) | `loady.cc` |
| Platform Core backend (OIDC/OAuth/API/JWKS) | `id.loady.cc` |
| Account Portal | `account.loady.cc` |
| Grand Admin | `admin.loady.cc` |

**Why**: zero new domain registration, zero new Cloudflare zone, only new
DNS *records* within the zone that already exists and already has working
TLS/Cloudflare proxy configuration. This is the path every prior mission
(5, 6, 7) has assumed by default — `platform-core/.env.production.example`
already hard-codes `PLATFORM_AUTH_BASE_URL=https://id.loady.cc` and
`PLATFORM_API_BASE_URL=https://id.loady.cc` as its example values (read
directly this mission), confirming this is the path of least resistance,
not a new proposal. It is also the lowest-risk option for TLS (see
`TLS_PLAN` below / Phase 14): a single wildcard `*.loady.cc` certificate (or
four SANs on one cert) covers all three new hostnames plus the apex with no
additional certificate-authority interaction beyond what likely already
exists for `loady.cc`.

## LONG-TERM OPTION

A separate, ecosystem-neutral domain (e.g. `platform.example.com` or a
dedicated brand domain) fronting all Platform Core surfaces, once — and
only once — a second real product beyond Loady goes into production and a
Loady-branded identity subdomain (`id.loady.cc`) stops making sense as the
shared login for users of an unrelated product. `MISSION_7_PRODUCTION_TOPOLOGY.md`
already documents this as option 2, explicitly deferred as "not needed for
this cutover."

**Why not now**: no second product is in production today (the demo
products and `sample-future-product-2` are development/test fixtures only,
per `MISSION_7_ARCHITECTURE_AUDIT.md` §4). Choosing a neutral domain before
it is needed adds a real domain-registration/DNS-zone/certificate cost with
no corresponding benefit yet, and the architecture does not require
deciding this now — see Migration Consequence below.

## MIGRATION CONSEQUENCE if the long-term option is chosen later

Moving from `id.loady.cc`/`account.loady.cc`/`admin.loady.cc` to a
different domain later is **not a code change** — every hostname is an env
var — but it is a real operational event with its own cutover
characteristics, distinct from this mission's identity/billing cutover:

1. A new TLS certificate covering the new domain must be provisioned before
   any traffic is pointed at it.
2. Every already-issued OIDC access/refresh token embeds the issuer
   (`iss`) claim as the current `PLATFORM_AUTH_BASE_URL` — changing the
   base URL invalidates every outstanding token's issuer check unless the
   old issuer is also accepted during a transition window. This is the same
   class of hard-cutover concern `KEY_ROTATION_RUNBOOK.md` documents for
   signing-key rotation, not a new mechanism to build, but it is a real
   consequence worth the owner knowing about before treating a domain
   change as "just a DNS edit."
3. Every registered OAuth client's redirect URI (Loady's, and any future
   product's) must be updated to the new `authorize`/`callback` hostname
   before the cutover, or logins for that client break atomically at the
   moment DNS/TLS switch over.
4. Bookmarked/saved links to the old Account Portal / Grand Admin hostnames
   would need a redirect (or would simply 404) unless the old hostname is
   kept alive as a redirect-only vhost for some transition period.

None of this blocks V1 production deployment — it is documented here so a
future domain-consolidation decision is made with the real consequence
known in advance, per Phase 4's instruction to flag the business decision
without blocking other prep on it.

## Decision status

This document does **not** unilaterally decide the domain — that is a real
business decision the owner must confirm (see
`HUMAN_INPUTS_REQUIRED_BEFORE_PRODUCTION.md`). Every other phase of this
mission proceeds using the **RECOMMENDED INITIAL CONFIGURATION** above as
its working assumption, exactly as every prior mission already did,
because it requires the least new infrastructure and matches the existing
`.env.production.example` defaults. If the owner instead chooses the
long-term option before cutover, only the hostname values change — no
phase's document needs to be re-architected, only its literal hostname
strings.
