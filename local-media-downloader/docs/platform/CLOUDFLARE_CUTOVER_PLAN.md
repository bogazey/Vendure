# Cloudflare Cutover Plan (Mission 15, Phase 13)

**Nothing in this document is performed by this mission.** No Cloudflare
zone was accessed, no DNS record was created, no setting was changed. This
is the exact plan for a human operator to execute later, using the
recommended hostnames from `IDENTITY_DOMAIN_DECISION.md`
(`id.loady.cc`, `account.loady.cc`, `admin.loady.cc`).

## DNS records to add (none exist today — three new records, zero changes to existing `loady.cc`/`www` records)

| Record | Type | Target | Proxy status |
|---|---|---|---|
| `id.loady.cc` | A (or CNAME to the same target `loady.cc` already resolves to) | Origin VPS IP (`185.2.103.46` — a known fact, not verified by this mission per the Absolute Safety Boundary) | **Proxied (orange cloud)** — same as `loady.cc` today |
| `account.loady.cc` | A/CNAME, same target | Proxied |
| `admin.loady.cc` | A/CNAME, same target | Proxied |

All three point at the **same** origin IP as `loady.cc` already does —
this is a single-VPS architecture; there is no separate origin server for
Platform Core. Name-based virtual hosting (already implemented in
`nginx.production.conf.template`) is what actually routes each hostname to
the right container once traffic reaches the shared origin.

## TLS mode

**Full (strict)** — matching what `docs/LAUNCH_CHECKLIST.md:53` already
requires for `loady.cc` today. Do not use Flexible or Full (non-strict)
for the new hostnames; using a weaker mode for only some hostnames on the
same zone would be an inconsistent, confusing security posture for no
benefit — see `TLS_CERTIFICATE_PLAN.md` (Phase 14) for exactly what
"valid origin certificate" requires for the three new hostnames
specifically.

## Origin certificate implications

See `TLS_CERTIFICATE_PLAN.md` for the full analysis. Summary: the exact
scope of the certificate `loady.cc` uses today (single-hostname,
`loady.cc`+`www.loady.cc` only vs. a wildcard `*.loady.cc`) is not
determinable from this repository — `PRODUCTION PREFLIGHT REQUIRED`. Full
(strict) mode will refuse the connection at the edge if the origin
presents a certificate that doesn't cover the requested hostname, so this
must be resolved **before** proxying any of the three new hostnames, not
discovered by trial and error against production traffic.

## Redirect considerations

- `nginx.production.conf.template`'s port-80 server block already issues a
  301 to https for **all four** hostnames in one block (`server_name
  ${RC_LOADY_HOSTNAME} www.${RC_LOADY_HOSTNAME} ${RC_PLATFORM_AUTH_HOSTNAME}
  ${RC_ACCOUNT_HOSTNAME} ${RC_ADMIN_HOSTNAME};`) — no per-hostname redirect
  configuration needed at the Cloudflare layer beyond enabling "Always Use
  HTTPS" (already a `LAUNCH_CHECKLIST.md` requirement for the existing
  zone) for the new hostnames too.
- No `www.` variant is needed for `id.`/`account.`/`admin.` — do not create
  `www.id.loady.cc` etc.; nothing references it.

## WAF / rate-limit considerations

- **Do not apply Loady's existing WAF/rate-limit rules blindly to the new
  hostnames** if any of Loady's rules are tuned around download/media
  traffic patterns (e.g. large response sizes, long-lived
  `/api/progress/stream` connections) — Platform Core's traffic profile is
  short JSON requests and OAuth redirects, a materially different shape.
  This mission has no visibility into Loady's actual configured WAF rules
  (Cloudflare dashboard state, not repo state) — `PRODUCTION PREFLIGHT
  REQUIRED` to review them before extending to the new hostnames.
- The OIDC `authorize`/`callback`/token-exchange endpoints on
  `id.loady.cc` are exactly the kind of endpoint a generic "block rapid
  repeated POSTs" WAF rule could break for a legitimate user retrying a
  failed login — flag for manual review, not a default-on rule.
- The Paddle webhook endpoint (`id.loady.cc/api/v1/billing/webhooks/paddle`,
  once billing cutover is separately authorized) must **never** be rate
  limited or challenged by a bot-management rule — Paddle's servers, not a
  browser, call it, and a CAPTCHA/JS-challenge response would look like a
  permanent delivery failure to Paddle. This is a real, specific
  configuration note operators must not overlook, called out because
  generic Cloudflare bot-management defaults commonly challenge
  server-to-server webhook traffic.

## Cache exclusions

The following must **never** be cached by Cloudflare (a "Cache Everything"
page rule or an aggressive default cache-everything setting would be a
correctness bug, not just a performance one, for these paths specifically):

- Every path under `id.loady.cc` — this is API/OIDC traffic; every response
  is either per-user (entitlement/session data) or must be freshly issued
  (authorization codes, tokens). No cache-control override is set for these
  routes in `nginx.production.conf.template` today, meaning Cloudflare's
  default caching behavior (which does not cache dynamic API responses
  without explicit cache headers by default) is the current safety net —
  **do not** add a blanket Cloudflare Cache Rule for `id.loady.cc/*`.
- `account.loady.cc`/`admin.loady.cc`'s own `/api/`, `/oauth/`,
  `/.well-known/` paths (added in Phase 12's fix) — same reasoning.
- The maintenance-mode response (Phase 21) — if Cloudflare caches the
  maintenance page's HTML response, users could keep seeing "under
  maintenance" after the window ends. **A Cloudflare Cache Rule bypassing
  cache for `loady.cc/*` during the maintenance window** (or, more simply,
  confirming no existing rule caches HTML responses with a `Retry-After`
  header) must be verified as part of the maintenance-window procedure —
  see `LOADY_PRODUCTION_CUTOVER_RUNBOOK.md`'s existing maintenance-mode
  handling and the final cutover runbook (Phase 26) for where this check
  is inserted as an explicit step. This closes the "no Cloudflare
  cache-purge/bypass procedure" gap identified in
  `FINAL_PREPRODUCTION_EVIDENCE_AUDIT.md` §8.
- Static assets (`/assets/*` on any of the four hostnames) are the
  **opposite** case — these are already marked `expires 1y; Cache-Control:
  public, immutable` at the nginx layer and *should* be cached by
  Cloudflare, unchanged from today's behavior for `loady.cc`.

## Explicitly not performed by this mission

- No DNS record created.
- No TLS mode changed.
- No WAF/rate-limit rule created or modified.
- No cache rule created or modified.
- No Cloudflare zone accessed in any way.
