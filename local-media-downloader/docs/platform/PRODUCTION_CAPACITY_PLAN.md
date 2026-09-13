# Production Capacity Plan (Mission 5, Phase 37)

**No production server was accessed to write this.** Per the Absolute
Safety Rule, real free RAM/disk/CPU on the production VPS were never
measured — this document estimates from (a) this repo's own deployment
docs (`docs/DEPLOYMENT.md`: "4-vCPU/8-GB beta VPS", consistent with the
mission brief's "Contabo Cloud VPS 4, Ubuntu 24.04" description) and (b)
real measurements taken from the staging rehearsal on this machine. Every
number below marked "measured" came from `docker stats` during or after
this mission's testing; everything else is an estimate explicitly labeled
as such.

## What's already running on the VPS (unchanged by this migration)

Per `compose.production.yml`: Loady's reverse-proxy, backend (Uvicorn,
`--workers 1`), and its own PostgreSQL — three containers, already sized
to fit comfortably in 4 vCPU / 8 GB (it's the box's current, working
production load).

## What Platform Core adds

| Container | Measured idle RSS (staging, this session) | Estimated production RSS under light load |
|---|---|---|
| `platform-core-backend` (Uvicorn, 1 worker) | ~77 MB | 150-250 MB (Python/FastAPI baseline plus per-request working set; staging saw this stay flat across dozens of requests and multiple outage/restart drills — no growth observed) |
| `platform-core-postgres` | not separately measured (shares the host's Docker Desktop VM budget in this rehearsal) | 100-300 MB for a database this size (tens of thousands of rows expected at Loady's actual user count, still a small database by Postgres standards) |
| `platform-core-admin-frontend` (static nginx) | negligible (serves a 245 KB JS bundle, gzip 78 KB) | <20 MB |
| `platform-core-reverse-proxy` (nginx) | negligible | <20 MB, shared if the topology in `PRODUCTION_TOPOLOGY.md` is followed (one edge nginx for both products, not a second one) |

**Total estimated addition: roughly 400-700 MB RAM, well under 10% of an
8 GB box**, plus disk for Platform Core's own Postgres data directory
(negligible at launch — single-digit MB for schema plus one row per
migrated user; will grow slowly, nowhere near Loady's own media-storage
footprint).

CPU: Platform Core's endpoints are lightweight (JWT verify/issue,
small indexed Postgres queries) — the load test in this mission (Phase
33) showed the health/readiness endpoints sustaining ~500 req/s at
concurrency 15 with 0% measured CPU load on this machine, and an
authenticated admin-list endpoint at ~25 req/s (single-worker, real
password/JWT verification per request) with equally negligible CPU.
Production traffic to Platform Core will be dominated by Loady's own
existing user base occasionally re-authenticating and Loady's backend
making server-to-server entitlement calls per download request — orders
of magnitude below what would stress a 4-vCPU box on its own.

## Likely resource contention

- **Disk I/O**: shared with Loady's own media downloads, which are
  already the dominant I/O consumer on this box (per
  `LMD_MAX_CONCURRENT_DOWNLOADS=1`, already tuned for this VPS size).
  Platform Core's own I/O footprint (small Postgres writes, no media) is
  not expected to meaningfully compete.
- **Memory**: the only real contention risk. If the VPS is already
  running close to its 8 GB ceiling under Loady alone, adding ~500 MB-1
  GB for Platform Core could matter — **this must be checked on the real
  box before cutover** (see below), not assumed from this estimate.
- **CPU**: not expected to be a meaningful constraint at Loady's current
  scale, based on the load-test numbers above; revisit if Loady's own
  user base has grown substantially since this document's estimates.

## Recommended container resource limits (mirroring Loady's existing pattern)

`compose.production.yml` already sets `deploy.resources.limits` on
Loady's own containers (e.g. reverse-proxy: 0.5 CPU / 256 MB). Platform
Core's production compose should follow the same convention:

| Container | Recommended CPU limit | Recommended memory limit |
|---|---|---|
| `platform-core-backend` | 0.5 | 512 MB |
| `platform-core-postgres` | 0.5 | 512 MB |
| `platform-core-admin-frontend` | 0.1 | 64 MB |
| `platform-core-reverse-proxy` (if not shared with Loady's — see `PRODUCTION_TOPOLOGY.md`) | 0.25 | 128 MB |

These are deliberately generous relative to the measured idle numbers
above (2-6x headroom) — tight enough to prevent one runaway container
from starving the box, loose enough not to throttle real traffic on a
box this size.

## Minimum free RAM/disk requirements for the production preflight

Recommend the go/no-go preflight (once pointed at real production, which
this mission never did) require, before cutover:

- **At least 1.5 GB free RAM** on the host (covers the ~700 MB estimate
  above plus a safety margin for the migration script's own peak memory
  use during the commit run, which processes the whole user table in
  memory in two phases — see `loady_migration_service.py`).
- **At least 2 GB free disk** (covers Platform Core's own Postgres data
  directory growth plus the pre-migration backup this runbook requires
  before every cutover — see `PRODUCTION_REHEARSAL_PLAN.md`'s PRE-MIGRATION
  section).

## Explicitly marked as a cutover preflight task, not done here

**Actual free RAM/disk/CPU headroom on the real production VPS must be
measured by an operator with real SSH access before cutover** — this
document provides planning estimates only. Add a concrete step to
`LOADY_PRODUCTION_CUTOVER_RUNBOOK.md`'s "24 hours before" section: `free
-h` and `df -h` on the real box, compared against the minimums above.
