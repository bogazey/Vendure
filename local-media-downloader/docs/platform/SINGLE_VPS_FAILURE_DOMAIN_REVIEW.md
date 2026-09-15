# Single-VPS Failure Domain Review (Mission 15, Phase 6)

Every failure below is analyzed against the frozen architecture
(`PRODUCTION_ARCHITECTURE_FREEZE.md`). This is a design-time analysis, not a
live fault-injection test against real hardware — real production behavior
under these conditions is `PRODUCTION PREFLIGHT REQUIRED`/`LIVE OBSERVATION
ONLY` as noted per row. Local fault-injection *within the constraints of
this environment* is covered separately in Phase 49.

There is **no high-availability claim anywhere in this document.** A
single VPS has no redundancy for compute, and this review does not pretend
otherwise — its purpose is to make every failure's *blast radius* explicit,
not to eliminate single points of failure that the single-VPS constraint
makes structurally unavoidable.

| Failure | What breaks | What keeps working | Login | Sessions | Downloads | Billing | Grand Admin | Account management |
|---|---|---|---|---|---|---|---|---|
| **Host CPU exhaustion** (e.g. runaway process, too many concurrent downloads even though Loady is capped at 1) | All containers slow down proportionally; healthchecks may start timing out and trigger Compose restarts, compounding the problem | Nothing is isolated from host-level CPU starvation — Docker CPU limits cap a container's *own* ceiling, they do not protect other containers from a starved host scheduler | Degraded (slow, possible timeout) | Degraded | Degraded/failing (yt-dlp/ffmpeg are CPU-bound) | Webhook processing delayed, not lost (Paddle retries on non-2xx/timeout) | Degraded | Degraded |
| **Host RAM exhaustion** | OOM killer targets the largest/most recently offending container (typically `backend` under load, given its 5G ceiling); Docker restarts it per `unless-stopped` | Other containers survive unless the OOM killer targets the host's own critical processes (rare, but possible if overcommitted, per the 7.5 GiB-limits-vs-8GB-host finding in Phase 5) | Interrupted during the restarted container's downtime, recovers after restart | Interrupted, recovers (state is in Postgres, not in-process) | Interrupted, recovers (in-flight job lost, matching existing single-worker behavior) | Webhook delivery may be missed if `platform-core-backend` is the one killed — Paddle's own retry schedule is the safety net, not this architecture | Interrupted if `platform-core-backend`/`platform-core-admin-frontend` killed, recovers | Interrupted, recovers |
| **Host disk exhaustion** | Postgres (either instance) refuses writes; SQLite (Loady's app/history DB) can corrupt on a write that runs out of space mid-transaction — this is the single scariest failure mode on this box, which is why Phase 20's backup-space preflight exists as a *separate, mandatory* gate before ever writing a backup | Read-only operations may continue briefly until disk fills further | New logins may fail (session/token writes); existing sessions may still validate via cached checks | Cannot create new sessions past this point | Fails immediately (yt-dlp/ffmpeg need disk for output; media volume shares the host filesystem) | Webhook processing fails to persist; Paddle retries, but repeated failure risks Paddle giving up per its own retry-exhaustion policy — `LIVE OBSERVATION ONLY` for exactly how many retries Paddle allows | Fails for any write (grant/revoke) | Fails for any write |
| **Docker daemon failure/restart** | Every container stops until the daemon returns; `unless-stopped` restart policy brings every container back once it does, in `depends_on: condition: service_healthy` order | Nothing — this is a full-stack outage by definition on a single host with one Docker daemon | Down | Down (but resumes cleanly — no data loss, Postgres/SQLite are durable) | Down, resumes | Down, resumes; any in-flight Paddle webhook during the outage is retried by Paddle | Down, resumes | Down, resumes |
| **Host restart (reboot)** | Same as Docker daemon failure, plus whatever time the OS itself takes to boot; `restart: unless-stopped` means containers auto-start once Docker starts, assuming Docker itself is enabled at boot (a host-level `systemctl enable docker`, `PRODUCTION PREFLIGHT REQUIRED` to confirm is actually set on the real VPS) | N/A | Down during reboot, resumes | Down, resumes | Down, resumes | Down, resumes | Down, resumes | Down, resumes |
| **Loady Postgres contention/failure** | Loady backend's commercial-DB-dependent routes fail (auth, plans, billing history reads) | Platform Core is entirely unaffected — separate Postgres instance, separate volume, separate credentials (by design, `PRODUCTION_ARCHITECTURE_FREEZE.md` §Volumes) | Loady's *local* login fails; a user relying on central SSO whose Loady-side account row lives in this same DB is equally affected — central SSO does not bypass Loady's own DB dependency for a Loady-specific session | Loady sessions fail; Platform Core's own sessions (Account Portal, Grand Admin) are unaffected | Fails (gating/history/credit logic all read this DB) | Loady's own Paddle webhook handler fails to persist (retried by Paddle); Platform Core's *separate*, not-yet-live billing stack is unaffected | Unaffected (different DB) | Unaffected for Platform-Core-side account data; Loady-specific account fields (if any) unaffected only insofar as they don't live in this DB |
| **Platform Core Postgres contention/failure** | Central login (OIDC token issuance/verification against DB-backed state), entitlement/capability resolution, Grand Admin, billing webhook processing all fail | Loady's own local login and local plan/entitlement logic (the pre-migration, non-central path) keep working — this is exactly the hybrid/fail-closed design `ENTITLEMENT_AVAILABILITY.md` and `platform_entitlement_service.py` implement | Central SSO login fails; Loady's local login (still present per the accepted V1 limitation in the architecture freeze) keeps working | Existing Loady sessions with an already-cached entitlement/status keep working for up to `entitlement_cache_ttl_minutes`/`session_revalidation_interval_minutes` (defaults 15/5 minutes) before failing closed to `Plan.FREE` per the documented fail-closed guarantee | Downloads gated by a cached-but-stale entitlement continue to work within the cache TTL window, then fail closed (degrade to Free-tier limits, not an outright error) — this is the "hybrid entitlement/cache behavior" Phase 6 explicitly asks to represent accurately, and it is a deliberate design choice already proven by Mission 5's rehearsal, not a bug | Platform Core's billing webhook endpoint fails to persist events; Paddle retries | Fails entirely (Grand Admin has no fallback — it *is* the Platform Core UI) | Fails entirely for centrally-managed accounts; Loady's own local account fields (if any remain) are unaffected |
| **`platform-core-backend` container crash-loops** (e.g. bad config, migration mismatch) | Same practical effect as Platform Core Postgres failure from Loady's perspective (the hybrid resolver can't reach it either way) | Loady's local fallback path, as above | Central SSO fails; Loady local login keeps working | Same bounded-cache behavior as above | Same bounded-cache behavior as above | Billing webhook endpoint unreachable; Paddle retries | Fails entirely | Fails entirely for centrally-managed accounts |
| **`reverse-proxy` (edge) crash** | All four public hostnames become unreachable simultaneously — this is the one true single point of failure introduced by the "one edge" design choice, made deliberately in `PRODUCTION_TOPOLOGY.md` to avoid "two competing TLS processes fighting over host port 443" | Nothing is reachable from the internet; internal container-to-container calls on `platform-net` (Loady backend → Platform Core backend) are unaffected since they bypass the edge entirely | Down | Down (no new requests reach any backend) | Down | Down (Paddle can't reach the webhook endpoint either; Paddle retries) | Down | Down |

## Summary: which failures are Loady-only, Platform-Core-only, or whole-stack

- **Whole-stack (any of the four hostnames down)**: Docker daemon failure,
  host restart, host disk exhaustion, edge container crash. These are
  unavoidable consequences of one host / one edge and are not mitigated
  further by this mission (no HA claim).
- **Loady-only** (Platform Core unaffected): Loady Postgres failure, Loady
  backend crash, Loady's own disk/media volume issues specific to
  downloads.
- **Platform-Core-only, Loady degrades but does not fully fail**: Platform
  Core Postgres failure, `platform-core-backend` crash. This is the
  hybrid-architecture's actual value: Loady was deliberately built
  (Missions 4-7) to survive Platform Core being unreachable, bounded by the
  cache TTLs above, rather than going down with it. This is the single most
  important failure-domain property this review confirms is real (code- and
  test-verified, not just claimed) rather than assumed.

## What this review does not claim

- It does not claim any failure recovers without operator intervention
  beyond Docker's own `restart: unless-stopped` — there is no auto-scaling,
  no failover host, no multi-region anything.
- It does not claim exact recovery timing for host-level failures (reboot
  duration, Docker daemon restart duration) — those are `PRODUCTION
  PREFLIGHT REQUIRED`/`LIVE OBSERVATION ONLY` and are carried into Phase 40's
  recovery-time-target document rather than guessed here.
