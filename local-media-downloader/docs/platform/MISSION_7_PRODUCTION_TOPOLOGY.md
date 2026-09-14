# Mission 7 — Final Production Topology

Status: DESIGN ONLY. Nothing in this document is deployed by Mission 7. No
production system is accessed. This extends `PRODUCTION_TOPOLOGY.md`
(Mission 5) with the piece it predates: **Account Portal**
(`platform-core/account-frontend`), built in Mission 6 after that document
was written. Read `PRODUCTION_TOPOLOGY.md` first — the network/port/backup
model it defines is unchanged and still correct; this document only adds
the missing surface and makes every hostname explicitly configurable, per
Mission 7 Phase 2's instruction not to assume new domains exist.

## Hostnames (all configurable — nothing below is a hard-coded assumption)

| Service | Suggested hostname | Env var that controls it |
|---|---|---|
| Loady frontend + backend | `loady.cc` (existing, real, unchanged) | `VITE_SITE_URL` / existing Loady config |
| Platform Core backend (OIDC/OAuth/API) | `id.loady.cc` (Mission 5's suggestion) or `auth.<domain>` per Mission 7's spec | `PLATFORM_AUTH_BASE_URL`, `PLATFORM_API_BASE_URL` |
| Account Portal | `account.loady.cc` or `account.<domain>` | `VITE_PLATFORM_API_BASE_URL` (Account Portal build arg) + reverse-proxy `server_name` |
| Grand Admin | `admin.loady.cc` or `admin.<domain>` (Mission 5's suggestion, unchanged) | `VITE_PLATFORM_API_BASE_URL` (admin-frontend build arg) + reverse-proxy `server_name` |

The user has not yet chosen a final domain structure. Until they do, the
recommended default keeps everything under the existing `loady.cc` zone
(subdomains only — no new domain purchase required), matching Mission 5's
original recommendation. This is documented separately so the choice can
be made independently of everything else in this mission — see the
**Recommended hostname structure** section at the end.

## Updated container map

Everything in `PRODUCTION_TOPOLOGY.md`'s diagram is unchanged except one
more internal service and one more edge `server{}` block:

```
                    nginx edge (host ports 80, 443 only — unchanged)
                         |            |              |            |
                    loady.cc     id.loady.cc   account.loady.cc  admin.loady.cc
                         |            |              |            |
                 [default network]   +--------[platform-net]------+
                         |            |              |            |
                  loady-backend  platform-core-  platform-core-  platform-core-
                         |         backend        account-       admin-frontend
                  loady-postgres      |            frontend           |
                                platform-core-  (NEW: nginx,     (nginx, static
                                  postgres       static build,    build, :80
                                  (NEW, no       :80 internal)    internal)
                                  host port)
```

### What's new vs. `PRODUCTION_TOPOLOGY.md`

- **`platform-core-account-frontend`** joins `platform-net` alongside
  `platform-core-admin-frontend`, same pattern (internal-only nginx
  container serving a static production build, no host port, proxied by
  the edge under its own hostname). Dockerfile/nginx.conf added this
  mission: `platform-core/account-frontend/Dockerfile`,
  `platform-core/account-frontend/nginx.conf` (mirrors
  `admin-frontend`'s, previously the only one of the two that existed).
- Edge nginx gets one more `server{}` block (`account.<domain>`) — see
  `platform-core/reverse-proxy/nginx.production.conf` (added this
  mission) for the combined, path-routed config covering all three
  Platform Core hostnames plus Loady's own.

No other network, port, database, secret, or backup-model change from
`PRODUCTION_TOPOLOGY.md` — that document's Networks, Ports, Databases,
Secrets, and Backups sections all still apply unmodified and are not
repeated here.

## Reverse proxy routes (all four hostnames, one edge container)

| Hostname | Path | Upstream |
|---|---|---|
| `loady.cc` | `/api/*` | `loady-backend:8000` |
| `loady.cc` | everything else | `loady-frontend` (static build, already how production works today) |
| `id.<domain>` (or `auth.<domain>`) | `/api/*`, `/oauth/*`, `/.well-known/*`, `/health`, `/ready` | `platform-core-backend:8000` |
| `account.<domain>` | everything | `platform-core-account-frontend:80` |
| `admin.<domain>` | everything | `platform-core-admin-frontend:80` |

## Health checks

Each internal service keeps its own container-level `HEALTHCHECK`
(unchanged from existing compose files); the edge additionally exposes
unauthenticated `/health` and `/ready` passthroughs for `id.<domain>` only
(Account Portal and Grand Admin are static builds with no backend of their
own to probe — their own container healthcheck, and the edge's proxy
health check against them, is sufficient).

## Resource limits, restart policies, dependency ordering

See `compose.rc.yml` (added this mission, Phase 18) for the concrete,
enforced `deploy.resources.limits` and `restart: unless-stopped` on every
service, and `docs/platform/MISSION_7_CAPACITY_PLAN.md` for the sizing
rationale. Dependency ordering (`depends_on: condition: service_healthy`)
is: `postgres` (both instances) → backend(s) → frontend(s) → edge —
identical pattern to both existing compose files, just applied uniformly
across the combined stack.

## Recommended hostname structure (for the user to decide, not assumed here)

Two real options, in order of recommendation:

1. **Subdomains of `loady.cc`** (`id.loady.cc`, `account.loady.cc`,
   `admin.loady.cc`) — zero new domain registration, zero new Cloudflare
   zone, only new DNS *records* within the zone that already exists. This
   is what both this document and `PRODUCTION_TOPOLOGY.md` assume by
   default and is the lowest-friction path to cutover.
2. **A separate ecosystem domain** (e.g. `platform.example.com` fronting
   all three Platform Core surfaces via its own sub-paths or subdomains)
   — only worth it if/when a second product beyond Loady goes into
   production and a Loady-branded subdomain for shared identity stops
   making sense. Not needed for this cutover; documented here only so the
   choice is visible, per Mission 7 Phase 2's instruction.

Either way, nothing in the container topology, reverse-proxy config
structure, or Compose file changes — only the `server_name` values and the
three `VITE_PLATFORM_API_BASE_URL`/`PLATFORM_AUTH_BASE_URL`/
`PLATFORM_API_BASE_URL` env vars change. This is exercised concretely by
`compose.rc.yml`, which takes every hostname as an env var with no
hard-coded default beyond `loady.cc` itself (already real, required).
