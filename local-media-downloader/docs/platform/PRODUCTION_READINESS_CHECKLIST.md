# Production Readiness Checklist

Status as of Mission 5 (supersedes the Mission 4 version below, updated
in place rather than duplicated). Categorized `BLOCKER` (must fix before
any real production migration) / `HIGH` / `MEDIUM` / `LOW` / `ACCEPTED
FOR INITIAL RELEASE`. Items marked ✅ were verified live in an actual
mission's staging rehearsal, not just implemented — Mission 5 items say
so explicitly where the verification is new.

**Judgment principle applied throughout (per the mission brief)**: a gap
is not automatically a BLOCKER merely because an enterprise-grade
solution exists elsewhere. Severity here reflects Loady's actual
deployment scale (a single VPS, one Uvicorn worker, a beta-stage user
base) and threat model, not a generic checklist.

## Identity

- ✅ **DONE** — Central identity, OAuth Authorization Code + PKCE,
  cross-product SSO, immutable `global_user_id` (Mission 3, re-verified
  live in this mission's cross-container rehearsal).
- `BLOCKER` — Ecosystem-wide logout does not exist (documented limitation
  since `LOADY_IDENTITY_INTEGRATION.md` §6, not addressed in this
  mission). Signing out of Platform Core does not sign a user out of
  Loady or vice versa.

## Database

- ✅ **DONE (Mission 5: outage behavior proven live, not just restart
  survival)** — a real Postgres outage (Platform Core's DB stopped, app
  process left running) was tested live: liveness stayed `ok`,
  readiness correctly reported `503`/`database:false`, an auth attempt
  failed safely (no corruption), and Loady's hybrid entitlement gate
  continued working from cache throughout. Full-stack restart (all
  containers, both stacks) left every dataset byte-identical, confirmed
  via direct row counts and a raw `diff` of the SQLite history file.
- `MEDIUM` (unchanged) — Pool sizing (5/10) is a single-worker-process
  guess, not load-tested at production scale. This mission's conservative
  load test (Phase 33: ~500 req/s on health/readiness, ~25 req/s on an
  authenticated admin endpoint, zero failures, zero measured memory
  growth) did not come close to stressing this pool — real traffic data
  is still needed before trusting the current sizing at scale.
- `MEDIUM` (unchanged) — No read replica / connection failover story.
  Single Postgres instance is a single point of failure (mitigated in
  practice by the hybrid entitlement cache for reads, proven live, but
  not for writes).

## TLS

- ✅ **DONE (staging only)** — Self-signed TLS terminated at an nginx
  reverse proxy, HTTP→HTTPS redirect, security headers, verified live
  over real HTTPS.
- `BLOCKER` — Self-signed certificate. Production needs a real
  certificate (Let's Encrypt, a commercial CA, or Cloudflare's own edge
  TLS) — not a code change, but not done here either.
- `HIGH` — Internal (service-to-service) traffic between Loady and
  Platform Core runs over plain HTTP on a private docker network in this
  staging design (see `STAGING_ARCHITECTURE.md`). Acceptable for a
  single-host staging rehearsal; a multi-host production deployment needs
  mTLS or an equivalently trusted private network.

## DNS

- Not touched, per mission constraints. `PLATFORM_AUTH_BASE_URL`/
  `PLATFORM_API_BASE_URL` are fully configurable and never hard-code a
  domain — production DNS decisions are unblocked by the architecture,
  but no DNS work has been done.

## Secrets

- ✅ **DONE** — No secret is committed; `.env.staging` added to
  `.gitignore`; signing key and token-encryption key both provisioned out
  of band via scripts that write to a gitignored `secrets/` directory.
- ✅ **DONE (Mission 5)** — full inventory documented
  (`PRODUCTION_SECRET_INVENTORY.md`): every secret's owner, consumer,
  storage requirement, rotation impact, and backup requirement, with zero
  values included.
- `HIGH` (unchanged) — No secret-manager integration (Vault, AWS/GCP
  Secrets Manager, etc.) — staging uses mounted files and `.env` files,
  adequate for staging, not for production secret rotation/audit
  requirements.

## Signing keys

- ✅ **DONE (Mission 5: failure modes proven live, not just restart
  survival)** — missing key → hard fail-closed container start failure
  (proven); wrong-but-valid key → app starts but issues tokens that are
  correctly rejected once the real key is restored, no algorithm
  confusion (proven); correct key → byte-identical across every restart
  and container recreation this session, never silently regenerated
  (proven via `diff`).
- ✅ **DONE (Mission 5)** — rotation procedure now documented
  (`KEY_ROTATION_RUNBOOK.md`), including a real operational gotcha found
  live (Docker Desktop can silently materialize an empty directory at a
  briefly-missing bind-mount source, requiring manual cleanup). No
  rotation **code/automation** was built — the runbook is manual, which
  is judged sufficient for the rotation frequency this key needs
  (infrequent, planned events, not routine).

## Token encryption

- ✅ **DONE (Mission 5: failure modes proven live)** — correct key
  works; wrong key, missing key, and directly-tampered ciphertext all
  fail safely (bounded-cache fallback, then fail-closed once the cache
  also expires), never crash, never leak plaintext/ciphertext/key
  material in logs (confirmed by reading actual container log output),
  and never auto-delete or silently overwrite an unreadable row
  (confirmed: a tampered row was still present, unchanged, after the
  test).
- `MEDIUM` (found this mission, documented) — the encryption envelope has
  no key-**version** field, so losing the encryption key without first
  re-encrypting every row under a new one makes that data permanently
  unrecoverable (not merely "hard to recover"). `KEY_ROTATION_RUNBOOK.md`
  documents the correct rotation sequence to avoid this (decrypt-with-old
  then re-encrypt-with-new before switching the active key), but no
  overlap/versioning mechanism exists for an *unplanned* key loss.
  Recommended follow-up, not a blocker for an initial migration (a single
  carefully-executed planned rotation doesn't need it).
- `MEDIUM` (unchanged) — No migration script has been run against a real
  legacy plaintext dataset (none exists yet in any real deployment) — the
  one-time re-encryption script (`encrypt_platform_oidc_tokens.py`) is
  written and unit-tested but has only been exercised against synthetic
  rows, never a production-scale table.

## Backup

- ✅ **DONE (Mission 5) — checksummed, independently verified restorable,
  and corruption-detection proven live.** `backup-before-platform-migration.sh`
  backs up both Postgres databases plus Loady's SQLite history file and
  a config/migration-version inventory (names only, never secret
  values); `verify-backup-restorable.sh` restores every artifact into
  throwaway, isolated resources and checks it. Corruption detection was
  proven, not assumed: a deliberately-corrupted **copy** of a real backup
  was correctly rejected before any restore attempt, while the original
  verified and restored cleanly.
- `BLOCKER` (unchanged) — No encryption of the backup file itself, no
  off-site storage, no automation/retention policy (see
  `PLATFORM_BACKUP_RESTORE.md`). Checksumming and restore-verification
  (this mission's additions) reduce but do not eliminate this gap — a
  backup that only ever lives on the same host as the database it backs
  up still does not survive that host's failure.

## Restore

- ✅ **DONE (Mission 5) — proven at the strongest available level: a real
  application actually running correctly against restored data**, not
  just "the tables are present." The rollback rehearsal (see above)
  restored a real backup into `loady-staging`'s live Postgres and
  confirmed real user logins, downloads, and local-billing plan
  resolution all worked correctly against it.
- `HIGH` (unchanged) — Only verified for a small, synthetic/staging-scale
  dataset (54-108 users depending on the run). Restore time at real
  production data volume is still unknown — `pg_restore` time scales
  with table size, and this was never measured against anything
  production-sized.

## Monitoring

- `HIGH` (unchanged, but now with a concrete plan) — No metrics/alerting
  pipeline. `/health` and `/ready` exist and are container-healthcheck-
  compatible, which is the minimum viable signal, but there is no
  dashboard, no alert-on-`/ready`-failing, and no log aggregation beyond
  structured stdout logging. `POST_MIGRATION_MONITORING.md` (Mission 5)
  maps every window (15 min through 72 hr) to signals this codebase
  already emits, so whatever platform is eventually stood up has a
  concrete integration target — but no new metric/alert infrastructure
  was built this mission.
- `LOW` (found this mission) — no counter/log line exists for the hybrid
  entitlement cache's live-vs-cached ratio, the one piece of genuinely
  new observable behavior this mission added. Cheap to add (one log
  line in `get_entitlement_hybrid`), not done here.

## Rate limiting

- ✅ **DONE** — In-memory sliding-window limiter on signup, login,
  password reset, OAuth token, and (new this mission) Grand Admin
  mutation endpoints.
- `HIGH` — Explicitly single-process/in-memory (documented in
  `rate_limit_service.py`'s own docstring, inherited from Loady's
  identical existing pattern). Running more than one backend worker
  process/replica would give each its own independent limit — i.e. the
  effective limit multiplies by worker count. Current staging/production
  Dockerfile runs `--workers 1` specifically to keep this true; scaling
  out requires a Redis-backed (or equivalent shared-state) limiter first.

## Email

- Untouched — `EMAIL_BACKEND=log` (dev/test only) is enforced by mission
  instruction; production Resend configuration was explicitly out of
  scope and not modified.

## Paddle

- Untouched. Loady staging is configured `PADDLE_ENV=sandbox` with all
  keys blank; nothing in this mission calls Paddle Live, and nothing here
  changes Loady's existing hard restriction to Paddle Sandbox.

## Migration

- ✅ **DONE (Mission 5) — executed for real against 51 synthetic users
  plus 4 real accounts**, not just re-confirmed dormant. Dry run proven
  zero-write; commit run proven idempotent at the row-count level across
  three consecutive runs; full reconciliation passed. Production Loady
  users have still never been migrated (per the Absolute Safety Rule) —
  this item's readiness is about the *tooling*, not about production
  having been touched.
- `MEDIUM` (found and fixed this mission) — `grant_or_change` created
  duplicate `Entitlement` rows on re-grant when the previous grant had
  already expired (a real, reachable scenario: a `past_due` subscription
  whose period end has passed). **Fixed**, with a regression test.
- `MEDIUM` (found this mission, not fixed) — see Entitlement availability
  above: re-running the full migration resyncs already-linked accounts'
  entitlements every time, which can silently overwrite a post-migration
  admin change.

## Rollback

- ✅ **DONE (Mission 5) — actually executed and timed**, not merely
  planned. A real, layered rollback (kill-switch + full Postgres restore
  from a checksummed, independently-verified backup) was run against
  `loady-staging`: 110 seconds total, old passwords confirmed working
  via local login with Platform Core fully disabled, all Loady-native
  data (users, history, local-billing plans) intact. A second migration
  was then run successfully against the rolled-back state (0 created, 52
  correctly skipped, same known conflict/failure as before) — rollback
  does not make re-migration impossible. See
  `PRODUCTION_ROLLBACK_REHEARSAL.md` for the full write-up, including the
  two real findings it surfaced (both already listed above/below).
- `LOW` — the measured 110s duration is for a 54-user staging database
  with the backup already on local disk; real production timing must add
  backup-retrieval time from wherever backups are actually stored
  (currently: nowhere off-server — see Backup below) and will scale
  somewhat with real user-table size.

## Session revocation

- ✅ **DONE (Mission 5) — measured, not estimated.** Real wall-clock
  polling against a hard-authentication endpoint measured **302 seconds**
  from a Grand Admin disable to Loady denying access, matching the
  documented 5-minute SLA almost exactly. See
  `PRODUCTION_REHEARSAL_PLAN.md` phase 18.
- `LOW` (found this mission) — the optional-auth download-creation
  endpoint (`POST /api/downloads`) degrades a disabled session to
  guest-tier rather than a flat 401, since it has an anonymous-guest
  fallback by design; the paid/gifted capability is still correctly and
  completely removed. See `MISSION_5_SECURITY_REVIEW.md` finding 3.
- `LOW` (found this mission) — a local disable is sticky: re-enabling an
  account centrally does not automatically restore Loady access (the
  early-exit check in `get_optional_user` skips re-validation once
  already locally disabled). Fails in the safe direction. See
  `MISSION_5_SECURITY_REVIEW.md` finding 4.
- `MEDIUM` (unchanged) — No background sweep; an idle-but-disabled
  session is only re-checked on its next request, which could be
  arbitrarily far in the future for a truly idle session.

## Entitlement availability

- ✅ **DONE (Mission 5) — now wired into the live download gate.** The
  hybrid model (Mission 4) is no longer just a proven-but-unconnected
  capability: `platform_entitlement_service.resolve_effective_plan()` is
  called from `routes_downloads.py` before every download authorization
  for accounts with a linked `global_user_id`. Live-verified end-to-end
  (Mission 5, phase 13): a Platform-Core-only Gifted Creator entitlement
  (zero local Loady `Subscription` row) correctly authorized a 4K
  download; a Free-plan migrated account was correctly blocked at 1080p
  and allowed at 720p in the same pass. The full outage/cache-expiry/
  recovery cycle (phases 14-17: Platform Core process down, its Postgres
  down, wrong/missing/tampered token-encryption key) was proven live to
  fail closed correctly in every case, never escalating a plan. This
  item is **no longer a BLOCKER**.
- `MEDIUM` (new, found this mission) — Re-running the full migration
  script after initial cutover resyncs (and can silently downgrade) an
  already-linked account's entitlement to match Loady's local
  subscription truth, discarding any Grand-Admin-only change made since.
  Mitigation: documented explicitly in the cutover runbook as "do not
  re-run routinely"; not fixed in code this mission.
- `LOW` (known, accepted) — Loady's account-page plan display still reads
  only the local `Subscription` row, so a Platform-Core-only gift is
  correctly *enforced* at the download gate but not yet *displayed*
  correctly on the account page. A UX inconsistency, not an
  authorization bug (see `ENTITLEMENT_AVAILABILITY.md`).

## Grand Admin

- ✅ **DONE (Mission 5: grant flow re-verified live via the real API)** —
  a real gifted-Creator grant was issued through the live
  `PATCH /api/v1/admin/users/{id}/entitlements` endpoint against a real
  migrated account, confirmed zero Paddle interaction and zero
  `PaymentRecord` rows, and confirmed the grant actually took effect at
  the download gate (see Entitlement availability above). User search and
  single-user detail views also exercised live via the real API.
- `UNTESTED (this mission)`: revoke, audit-log viewing via the API, and
  product-scoped-administrator restrictions were not independently
  re-exercised this pass (Mission 3's own tests and live rehearsal cover
  them; not re-run live here).
- Not re-verified this mission: EN/AR/RTL rendering and unauthorized-access
  UI behavior in a real browser (only the API layer was exercised live;
  the admin-frontend's own unit tests, which do cover i18n/RTL, still
  pass — 7/7, unchanged).

## Maintenance mode

- ✅ **DONE (Mission 5, new)** — a single `MAINTENANCE_MODE` flag,
  checked per-request (no restart needed to toggle), blocks every
  mutating request with a clear `503`/`MAINTENANCE_MODE` response while
  leaving `GET`/`HEAD`/`OPTIONS` and the health check unaffected.
  Live-verified against staging: signup blocked while on, normal
  operation resumed immediately once turned off, no data loss.
  Deliberately simple (a boolean, no scheduling) — sufficient for the
  5-15 minute window this migration needs, per the mission's own
  "don't build an overly complex zero-downtime migration" guidance.

## Load / concurrency

- ✅ **DONE (Mission 5, conservative)** — health/readiness endpoints
  sustained ~500 req/s at concurrency 15 with zero failures; an
  authenticated admin endpoint sustained ~25 req/s (expected, given real
  password/JWT verification per request and a single Uvicorn worker) also
  with zero failures. Memory stayed flat (~77-95 MB per backend
  container) across this entire mission's extensive testing — no leak
  signature observed. The existing rate limiter was confirmed still
  functioning correctly under this load (429s after repeated failed
  logins, exactly as designed).
- `LOW` — this was a conservative smoke test, not a stress test to
  failure — actual production capacity limits (especially for the
  single-worker/in-memory-rate-limiter architecture, already flagged
  HIGH under Rate limiting) remain unmeasured beyond this.

## Audit logs

- ✅ **DONE (Mission 3, unchanged)** — Append-only, never contains
  secrets/tokens/password hashes.

## Privacy

- No new PII is collected by anything built in this mission. Existing
  privacy posture (Mission 3, `SECURITY.md`) unchanged.

## Incident recovery

- ✅ **DONE (Mission 5), partial** — key rotation now has a documented
  procedure (`KEY_ROTATION_RUNBOOK.md`, covering signing key, token
  encryption key, and OAuth client secret) and objective rollback
  triggers are defined (`LOADY_PRODUCTION_CUTOVER_RUNBOOK.md` section P).
- `HIGH` (narrowed, not closed) — "What to do if Platform Core's database
  is compromised" (as opposed to merely unavailable, which is now
  thoroughly covered) is still unwritten — a compromise scenario implies
  needing to also consider whether issued tokens/backups from before
  the compromise are trustworthy, which this mission did not address.

## One-time Loady re-login

- ✅ **DONE (Mission 5) — re-verified live, directly, not just carried
  forward.** A real account's original Loady password was confirmed to
  authenticate successfully directly against Platform Core after
  migration, and the full Authorization Code + PKCE flow was driven
  end-to-end via real HTTP calls (not a browser, but the real server-side
  code path), correctly resolving to the same local Loady account by
  `global_user_id`.

## Cross-product SSO

- ✅ **DONE (Mission 3)** — the same underlying OAuth/PKCE mechanism
  proven for Loady in Mission 5's live rehearsal (phase 10, real
  end-to-end Authorization Code + PKCE flow) is architecturally identical
  to what SSOs demo products A/B.
- `UNTESTED (this mission)` — demo-product-a/b run as plain
  uncontainerized dev processes and were **not started or independently
  re-exercised** in Mission 5's rehearsal (a time-boxed choice, stated
  plainly rather than assumed fine). Coverage for this specific claim
  rests on Mission 3's own live browser rehearsal plus the still-passing
  automated `test_cross_product.py` suite (part of the 77 Platform Core
  tests), not a fresh live run this mission.

## Consolidated summary (Mission 5, Phase 36 classification)

**Remaining BLOCKERs** (must fix before any real production migration):
1. Backup encryption-at-rest, off-site storage, and automation (Backup).
2. Ecosystem-wide logout does not exist (Identity).
3. Self-signed TLS in staging — production needs a real certificate
   (TLS) — not a code change, but genuinely unstarted.

**Remaining HIGH**:
1. No secret-manager integration (Secrets).
2. Internal service-to-service HTTP is unencrypted on the shared staging
   network (TLS) — acceptable for a single-host deployment per
   `PRODUCTION_TOPOLOGY.md`'s design, a real gap only if a future
   multi-host deployment is planned.
3. Rate limiter is in-memory/single-process (Rate limiting) — bounded by
   the existing `--workers 1` constraint, which this mission did not
   change or need to change.
4. No metrics/alerting pipeline (Monitoring) — a concrete integration
   plan now exists (`POST_MIGRATION_MONITORING.md`), but no
   infrastructure was stood up.
5. Restore time at real production data volume is unmeasured (Restore).
6. "Database compromised" incident procedure is unwritten (Incident
   recovery) — narrower than before Mission 5, but not closed.

**MEDIUM findings from this mission** (all documented, most not code-fixed):
1. Migration re-run resyncing/overwriting already-linked accounts'
   entitlements (fixed at the row-duplication level; the resync-on-every-run
   *behavior* itself is documented as an operational constraint, not
   changed in code).
2. `grant_or_change` duplicate-row bug — **fixed**, with a regression test.
3. Token-encryption envelope has no key-version field, making an
   unplanned key loss unrecoverable (a planned, careful rotation avoids
   this; documented in `KEY_ROTATION_RUNBOOK.md`).
4. No background sweep for idle disabled sessions (pre-existing,
   unchanged).
5. Postgres connection pool sizing unvalidated at real load.

**ACCEPTED FOR INITIAL RELEASE** (judged acceptable at Loady's actual
scale/threat model, not merely convenient to defer):
1. Guest-tier fallback on a disabled account's download endpoint (LOW —
   never escalates beyond what an anonymous visitor already gets).
2. Local-disable stickiness across a central re-enable (LOW — fails
   safe, self-corrects on next login).
3. No hybrid-cache-source metric (LOW — one log line away, genuinely
   low priority next to the BLOCKERs above).
4. Cross-product SSO not independently re-exercised against the demo
   products this mission (covered by Mission 3's live rehearsal +
   passing automated tests; re-running it live would have been
   marginal additional evidence for the time cost).
5. Single-VPS architecture / resource contention with existing Loady —
   `PRODUCTION_CAPACITY_PLAN.md`'s estimates show comfortable headroom
   (~500 MB-1 GB addition to an 8 GB box); real headroom must still be
   measured on the actual VPS before cutover, tracked as a preflight
   task, not a blocker to preparing for cutover.
6. Local-only public DNS/Cloudflare testing — genuinely cannot be done
   without production access; the architecture (configurable base URLs,
   no hardcoded domains) is unblocked by this, which is what a
   pre-production mission can actually control.
