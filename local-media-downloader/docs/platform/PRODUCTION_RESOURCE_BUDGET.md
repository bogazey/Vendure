# Production Resource Budget (Mission 15, Phase 5)

Every number below except the Docker `deploy.resources.limits` values is an
**estimate carried from `PRODUCTION_CAPACITY_PLAN.md`**, not a fresh
measurement — this mission has no more access to the real VPS than that
prior mission did. Where this document adds a number Docker will actually
enforce (the `limits:` column), it is read directly from `compose.rc.yml`.

## Per-container budget

| Container | CPU limit | Memory limit | Restart policy | Healthcheck | Expected idle footprint | Failure behavior |
|---|---|---|---|---|---|---|
| `reverse-proxy` | 0.50 | 256M | `unless-stopped` | `wget --spider https://127.0.0.1/robots.txt` every 30s | Low — static file serving + proxying, no app logic | Container restart (Compose) brings it back; **all four hostnames go down simultaneously** while it is down — single point of failure by design (one edge, per architecture freeze) |
| `backend` (Loady) | 3.00 | 5G | `unless-stopped` | `curl --fail http://127.0.0.1:8000/api/health` every 30s, 30s start_period | Documented existing baseline (unchanged by this mission) | Loady downloads/history/auth all fail; Platform Core is unaffected (independent container/DB) |
| `postgres` (Loady) | 0.75 | 1G | `unless-stopped` | `pg_isready` every 10s | Documented existing baseline | Loady backend loses its commercial DB; Loady's SQLite-backed history/app data is unaffected (different storage) |
| `platform-core-postgres` | 0.50 | 512M | `unless-stopped` | `pg_isready` every 10s | New — a mostly-idle Postgres instance (identity/entitlement/billing rows only, no media/download load) | Platform Core backend loses its DB — see the failure-domain review (Phase 6) for exactly what breaks in Loady as a result |
| `platform-core-backend` | 1.00 | 512M | `unless-stopped` | Python urllib GET `/health` every 30s, 30s start_period | New — OIDC/API traffic only, no media processing | Central login, entitlement lookups, Grand Admin API, billing webhook all fail; Loady's own cached/fail-closed behavior (see `ENTITLEMENT_AVAILABILITY.md`) determines how gracefully Loady degrades |
| `platform-core-account-frontend` | 0.25 | 128M | `unless-stopped` | None declared (static nginx; the edge's own proxy failure is the effective signal) | New — negligible, static file serving | Account Portal UI unreachable; does not affect Loady or Platform Core's API |
| `platform-core-admin-frontend` | 0.25 | 128M | `unless-stopped` | None declared (same reasoning) | New — negligible | Grand Admin UI unreachable; does not affect Loady or the API |

**Sum of all Docker memory *limits* (not usage) across all 7 containers:
256M + 5120M + 1024M + 512M + 512M + 128M + 128M = 7,680 MiB (7.5 GiB).**
This is a ceiling, not a reservation — Docker only enforces it as an
out-of-memory kill point per container, it does not pre-allocate it. But it
is the number that matters for the failure-domain question "could every
container simultaneously max out its limit and exceed host RAM": if the
real VPS has 8 GB total RAM (the figure `PRODUCTION_TOPOLOGY.md` assumed,
never confirmed against the real box), **7.5 GiB of limits leaves under
512 MiB of headroom for the host OS, Docker daemon, and any other process**
— tight enough that this mission flags it as a real capacity risk, not
just a documentation nicety. See the GO/NO-GO threshold below.

**Sum of CPU limits**: 0.50 + 3.00 + 0.75 + 0.50 + 1.00 + 0.25 + 0.25 = 6.25
vCPU-equivalents. Docker CPU limits are soft (CFS quota, not a hard
partition), so this does not need to fit inside the physical core count the
way memory limits do, but a VPS with fewer than ~6-7 vCPUs would see
meaningful CPU contention if every container were simultaneously busy.
"Cloud VPS 4" (Contabo's naming) is not independently confirmed to have any
particular vCPU count by this mission — `PRODUCTION PREFLIGHT REQUIRED`.

## Explaining the limits vs. actual usage distinction (per Phase 5's requirement)

`deploy.resources.limits` in `compose.rc.yml` is Docker Compose's per-container
ceiling — the container is killed/throttled if it exceeds `memory`/`cpus`
respectively, but ordinary operation is expected to use well under the
limit for every container except `backend` (Loady), which is documented
elsewhere as legitimately needing up to its 5 GiB ceiling under a real
concurrent-download load (yt-dlp + ffmpeg processes are memory-hungry per
active job, and Loady is configured for exactly one simultaneous job —
`LMD_MAX_CONCURRENT_DOWNLOADS=1` in `.env.production.example`). Platform
Core's own containers are expected to run far below their limits in normal
operation (400-700 MB / 500 MB-1 GB total across `platform-core-backend`
+ `platform-core-postgres`, per `PRODUCTION_CAPACITY_PLAN.md` lines 29/54 —
see `FINAL_PREPRODUCTION_EVIDENCE_AUDIT.md` §5 for the internal
inconsistency between those two numbers, resolved below).

## Preflight thresholds (this mission's single authoritative numbers, superseding both of `PRODUCTION_CAPACITY_PLAN.md`'s internally-inconsistent estimates and reconciling them with `preflight-production-migration.sh`'s own hardcoded check)

| Threshold | Value | Rationale |
|---|---|---|
| Minimum free disk (before starting Platform Core containers) | **≥ 5 GiB** | Matches `preflight-production-migration.sh`'s existing hardcoded check (stricter than `PRODUCTION_CAPACITY_PLAN.md`'s own stated 2 GB minimum) — kept as the one authoritative number rather than loosened |
| Minimum free RAM (before starting Platform Core containers) | **≥ 2 GiB** | Rounds `PRODUCTION_CAPACITY_PLAN.md`'s higher 500 MB-1 GB estimate up with real margin, given the 7.5 GiB total-limits finding above leaves little room for error |
| Maximum acceptable 1-minute load average at preflight time | **< number of host vCPUs** (exact vCPU count is `PRODUCTION PREFLIGHT REQUIRED`) | Standard "not already CPU-saturated" heuristic; cannot be expressed as an absolute number until the real core count is known |
| Swap pressure | **`swapped-out` pages should be 0 or trivial** at preflight time; any active swapping is a NO-GO signal, not a warning | Given the tight memory-limit headroom above, active swapping before Platform Core even starts means the box has no real margin |
| Platform Core Postgres free space (post-creation) | **≥ 1 GiB free in the volume** beyond the database's current size | Identity/entitlement/billing rows are small individually; this is a generous floor, not a tight one |
| Docker volume free space (general) | Same 5 GiB host-disk floor above covers this — Docker volumes share the host filesystem in this single-VPS design, there is no separate volume-level quota | N/A |

Anything above marked as needing the real VPS's numbers is
`PRODUCTION PREFLIGHT REQUIRED` and is implemented as an actual check in
Phase 18's read-only preflight script, not left as a paper threshold only.
