# TLS Certificate Plan (Mission 15, Phase 14)

## What is known from the repository

- Production TLS mode is Cloudflare Full (strict) (`docs/LAUNCH_CHECKLIST.md:53`,
  `docs/DEPLOYMENT.md:51`) — the origin must present a certificate
  Cloudflare itself validates (either a publicly-trusted CA certificate, or
  a Cloudflare Origin CA certificate, both satisfy Full (strict); a
  self-signed certificate does not).
- The certificate is mounted into the edge container at
  `/etc/nginx/tls/fullchain.pem` / `/etc/nginx/tls/privkey.pem`
  (`frontend/nginx.tls.conf`, unchanged, and identically in
  `nginx.production.conf.template` for all four hostnames — all share one
  mount point, meaning **one certificate file must cover all four
  hostnames**, not four separate certificate files, unless the compose
  file and template are further changed to mount per-hostname certs —
  out of scope, since a single multi-SAN or wildcard cert is simpler and
  is what the template already assumes).
- `docs/DEPLOYMENT.md`/`docs/LAUNCH_CHECKLIST.md` say "install a valid
  origin certificate" without naming a specific provisioning tool
  (certbot/Let's Encrypt vs. Cloudflare's own Origin CA) — the actual
  mechanism used for the current `loady.cc` certificate is not recorded
  anywhere in this repository.

## What is NOT knowable from the repository — `PRODUCTION PREFLIGHT REQUIRED`

1. **Whether the current certificate is single-hostname (`loady.cc` +
   `www.loady.cc` only) or already a wildcard (`*.loady.cc` + apex).** This
   is the single most important fact for this phase: if it is already a
   wildcard, **zero certificate work is needed** for `id.`/`account.`/
   `admin.loady.cc` — they are already covered. If it is single-hostname
   (e.g. a Let's Encrypt cert requested for exactly `loady.cc,www.loady.cc`),
   a new certificate covering the three new subdomains must be requested
   before those hostnames can be proxied in Full (strict) mode.
2. **Which CA/tool issued it** (Let's Encrypt/certbot, Cloudflare Origin
   CA, or another provider), which determines the renewal/reissuance
   procedure to add the new hostnames.
3. **Whether an existing renewal automation (e.g. a certbot cron/systemd
   timer) would need its own hostname list updated**, or whether it is
   manually managed.

## Two paths, both safe, neither performed by this mission

### Path A — the existing certificate is (or is reissued as) a wildcard `*.loady.cc` + apex

Simplest path. One certificate continues to cover `loady.cc`, `www.loady.cc`,
`id.loady.cc`, `account.loady.cc`, `admin.loady.cc`, and any future
subdomain, with no further reissuance needed for future Platform Core
surfaces. If using Let's Encrypt, a wildcard requires **DNS-01 challenge
validation** (not HTTP-01), which requires either Cloudflare API
credentials for automated DNS record creation during renewal, or a manual
renewal process — a real operational detail to nail down, not assumed
away here.

### Path B — a multi-SAN certificate listing all five hostnames explicitly

`loady.cc, www.loady.cc, id.loady.cc, account.loady.cc, admin.loady.cc` as
Subject Alternative Names on one certificate. Works with either HTTP-01 or
DNS-01 validation (Let's Encrypt) since every name is explicit. Requires
reissuance (not just renewal) every time a new Platform Core hostname is
added in the future (e.g. if the long-term domain option in
`IDENTITY_DOMAIN_DECISION.md` is ever adopted) — a real but acceptable
maintenance cost for V1, and arguably clearer/more auditable than a
wildcard for a small, known set of hostnames.

**This mission does not recommend one over the other** — it is an
operational/tooling decision that depends entirely on facts this mission
cannot access (which CA/tool is already in use). Whichever path is chosen,
`nginx.production.conf.template`'s single shared mount point for all four
hostnames' cert/key requires no further code change either way — both
paths produce one `fullchain.pem`/`privkey.pem` pair.

## Never expose private keys

- The private key never appears in this document, any other document this
  mission wrote, any log, or any command's captured output.
- `RC_TLS_DIR`'s host directory must be `chmod 600`/root-owned equivalent,
  matching `PRODUCTION_SECRET_STORAGE_PLAN.md`'s general file-permission
  posture — the key is mounted read-only (`:ro`) into the container per
  `compose.rc.yml`, but the host-side file permissions are what actually
  prevent an unrelated process on the same VPS from reading it.

## Validation performed this mission

`nginx -t` was run against the rendered `nginx.production.conf.template`
using a throwaway, 1-day, locally-generated self-signed certificate purely
to satisfy the `ssl_certificate` directive's file-existence check during
syntax validation (`PRODUCTION_REVERSE_PROXY_REVIEW.md`) — this proves the
config *references* the certificate paths correctly, not that a real,
CA-valid certificate for the new hostnames exists. That remains
`PRODUCTION PREFLIGHT REQUIRED`.
