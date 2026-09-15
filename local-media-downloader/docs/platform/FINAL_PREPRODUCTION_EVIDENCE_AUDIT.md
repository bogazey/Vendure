# Final Pre-Production Evidence Audit (Mission 15, Phase 1)

**Purpose**: reconcile every prior mission's documentation and code into one
authoritative evidence ledger before any further pre-production work is
written. Every non-trivial conclusion this mission relies on is classified
into exactly one of the eight tiers below. **A conclusion is never upgraded
past what was actually demonstrated** — if the only evidence for something
is a paragraph of prose in an earlier mission's doc, it stays classified
`DOCUMENTED ONLY` here even if that earlier doc sounded confident.

## Verification tiers (definitions used consistently for the rest of this mission)

| Tier | Meaning |
|---|---|
| `CODE VERIFIED` | The behavior is directly readable in the shipped source, not merely described. |
| `UNIT TEST VERIFIED` | An automated test in the repo exercises the specific behavior and is part of the suite that must stay green. |
| `INTEGRATION TEST VERIFIED` | A test exercises the behavior across a real service boundary (e.g. a real Postgres container, two cooperating services), not just in-process mocks. |
| `LOCAL LIVE-STACK VERIFIED` | Demonstrated by actually running the stack (processes/containers) locally and observing the result, not just tests. |
| `SANDBOX VERIFIED` | Demonstrated against a real third-party Sandbox (Paddle Sandbox), using a real captured event, not a hand-built fixture. |
| `DOCUMENTED ONLY` | Asserted in a doc or design note, with no test or live run backing it. Treated as an unverified claim until proven otherwise. |
| `PRODUCTION PREFLIGHT REQUIRED` | Can only be known by inspecting the real production host/services; not knowable from the repo. |
| `LIVE OBSERVATION ONLY` | Can only ever be confirmed once real production/Live traffic exists; no amount of local or Sandbox work can close this gap. |

## 1. Architecture and topology (Mission 7)

| Conclusion | Tier | Source |
|---|---|---|
| Single-VPS coexistence architecture (Loady + Platform Core sharing one Docker host via a dedicated `loady-rc` Compose project, `platform-net` internal network, Nginx-based reverse proxy fronting both) is already fully designed, not something this mission needs to invent | `CODE VERIFIED` | `compose.rc.yml` (265 lines), `platform-core/reverse-proxy/nginx.production.conf.template`, `docs/platform/MISSION_7_PRODUCTION_TOPOLOGY.md`, `docs/platform/MISSION_7_ARCHITECTURE_AUDIT.md` |
| `compose.rc.yml`'s `reverse-proxy` service is hardened (`read_only`, `tmpfs`, `cap_drop: ALL` + minimal `cap_add`, `no-new-privileges`, healthcheck, resource limits) | `CODE VERIFIED` | `compose.rc.yml` lines 30-82 (read directly this mission) |
| Platform Core backend and Loady backend both run as non-root (`uid 10101/gid platform`, `uid 10001/gid loady`) under `tini` | `CODE VERIFIED` | `platform-core/backend/Dockerfile`, `backend/Dockerfile` (read directly this mission) |
| `compose.rc.yml` combines Loady's *existing, unchanged* `compose.production.yml` + `compose.tls.yml` with Platform Core's services under one project name (`loady-rc`) | `CODE VERIFIED` | `compose.rc.yml` header comment + service list (`reverse-proxy`, `backend`, `postgres`, `platform-core-postgres`, `platform-core-backend`, `platform-core-account-frontend`, `platform-core-admin-frontend`) |
| This combined stack has actually been brought up and its services observed healthy together | `DOCUMENTED ONLY` — no Docker daemon exists in any environment this mission or Mission 7 ran in per its own text; `docker compose config` (pure YAML validation) is the only mechanically-checked thing | `MISSION_7_ARCHITECTURE_AUDIT.md` self-describes this limitation |
| Actual free CPU/RAM/disk on the real production VPS today | `PRODUCTION PREFLIGHT REQUIRED` | Explicitly out of scope for every prior mission; restated as a hard constraint by this mission |

**Dangling reference found**: `docs/platform/MISSION_7_PRODUCTION_TOPOLOGY.md:91` cites
`docs/platform/MISSION_7_CAPACITY_PLAN.md` for sizing detail. That file does
not exist (confirmed via `ls docs/platform/`). The sizing content that file
would have held instead lives in `docs/platform/PRODUCTION_CAPACITY_PLAN.md`
(99 lines, present). Likely the file was renamed during Mission 7 and the
cross-reference was never updated. **Treated as closed by pointing all Phase
5 work at `PRODUCTION_CAPACITY_PLAN.md`, not by creating the missing file.**

**Second dangling reference found**: the same pattern was searched for
`MISSION_7_DNS_TLS_RUNBOOK.md` — also referenced by name in at least one
prior mission's planning notes and also absent. No DNS/TLS runbook narrower
than `docs/platform/CLOUDFLARE_CUTOVER_PLAN.md` (this mission, Phase 13) and
this mission's TLS plan (Phase 14) exists; those two deliverables are this
mission's answer to the gap, not a recovery of a lost file.

## 2. Identity migration (Mission 3, re-audited Mission 6/7)

| Conclusion | Tier | Source |
|---|---|---|
| `loady_migration_service.run_migration` correctly matches by immutable `global_user_id` first, then email, is idempotent on re-run for an unlinked user, and produces a structured report (created/linked/skipped/conflicted/failed) | `UNIT TEST VERIFIED` | `platform-core/backend/app/services/loady_migration_service.py` + its test suite (part of the 284 Platform Core tests) |
| Argon2id password hashes migrate byte-for-byte compatibly (no re-hash, no forced reset) | `UNIT TEST VERIFIED` | Mission 3's dedicated hash-compatibility test (task #96) |
| **Known, unfixed defect**: re-running `run_migration --commit` for a user who is *already linked* re-derives that user's entitlement from Loady's current plan state, which can silently downgrade a Grand-Admin-issued gift back to the Loady plan (e.g. `free`) if migration is re-run after the gift was granted | `CODE VERIFIED` (the overwrite path itself) / `DOCUMENTED ONLY` (that it "won't happen in practice") | Identified in a prior mission's audit and explicitly left unfixed as out of scope at the time; re-confirmed present in the current `loady_migration_service.py` this mission. **This is the practical answer to Phase 39 ("rollback point of no return")**: migration must not be re-run with `--commit` after any Grand Admin gift action for already-migrated users without first checking for existing `GiftedAccess` rows. |
| Dry-run mode performs zero writes to either database | `UNIT TEST VERIFIED` + `CODE VERIFIED` (module docstring explicitly documents this contract) | `loady_migration_service.py`, `LOADY_MIGRATION_DRY_RUN.md` |
| The migration has been run against real production Loady data | `PRODUCTION AUTHORIZATION` (not evidence — this is a future authorized action, and is explicitly forbidden in this mission) | N/A |

## 3. Billing ownership transition (Missions 8-14)

| Conclusion | Tier | Source |
|---|---|---|
| Refund lifecycle (`adjustment.created` pending_approval → `adjustment.updated` approved) applies its financial/entitlement effect exactly once, verified against **real captured Paddle Sandbox event shapes** | `SANDBOX VERIFIED` + `UNIT TEST VERIFIED` | `tests/test_real_evidence_adjustment_lifecycle.py`, `tests/test_paddle_provider_normalization.py`, both read in full this mission; fixtures are sanitized real captures per `BILLING_OWNERSHIP_TRANSITION.md` §6d |
| Redelivery of the same `adjustment.updated` event never double-refunds | `SANDBOX VERIFIED` + `UNIT TEST VERIFIED` | `test_redelivering_the_same_approved_event_never_double_applies` |
| `subscription.updated`'s `current_billing_period`/`scheduled_change` extraction matches Paddle's real field names/nesting | `SANDBOX VERIFIED` | `TestSubscriptionUpdatedNormalizationAgainstRealPayload` |
| Gifted/internal/lifetime entitlements survive a Paddle refund/chargeback revoking the same product's Paddle entitlement (`GiftedAccess.external_ref` shadow-record mechanism) | `UNIT TEST VERIFIED` | Mission 12, 19 dedicated tests, `BILLING_OWNERSHIP_TRANSITION.md` §6c |
| Chargeback/dispute event shape and lifecycle (status transitions, whether `pending_approval`/`approved`/`rejected`/`reversed` apply the same way as refunds) | `LIVE OBSERVATION ONLY` | `PADDLE_LIVE_INPUTS_REQUIRED.md` §4/§4a — confirmed programmatically that this Sandbox account's simulator catalog has **no chargeback scenario at all**, not merely untried. No amount of further Sandbox work can close this; only a real Live dispute can. Carried forward unchanged into this mission (Phase 16 restates it; it is **not** re-litigated as a Sandbox gap). |
| The existing conservative "immediate-revoke, no grace period" handling for chargebacks is the correct default until real evidence exists | `DOCUMENTED ONLY` (a design decision, not something evidence can verify further pre-Live) | `PADDLE_LIVE_INPUTS_REQUIRED.md` §5 Decision #1 |
| Zero mismatches found between `paddle_provider.py`'s normalization and real Sandbox event shapes for every event type captured so far | `SANDBOX VERIFIED` | Missions 9 and 14 audits, both closed with "zero mismatches" |
| Platform Core has actually processed a real Paddle **Live** webhook | Not applicable — `LIVE OBSERVATION ONLY` until Stage 2/3 of `BILLING_CUTOVER_RUNBOOK.md` is authorized and executed | N/A |

## 4. Backup, restore, rollback

| Conclusion | Tier | Source |
|---|---|---|
| Backup scripts produce a checksummed, timestamped artifact and a separate restore-verification script proves the backup is actually restorable (not just "exit 0") | `LOCAL LIVE-STACK VERIFIED` (rehearsed against synthetic local data) | `scripts/platform/backup-before-platform-migration.sh`, `scripts/platform/verify-backup-restorable.sh` |
| These scripts have been measured at production scale (real row counts, real disk I/O characteristics) | `DOCUMENTED ONLY` — only ever rehearsed at small synthetic-staging scale | `PRODUCTION_REHEARSAL_PLAN.md`, `PRODUCTION_ROLLBACK_REHEARSAL.md` |
| Root-level `scripts/restore-rehearsal.sh` is a stale, weaker predecessor to `scripts/platform/verify-backup-restorable.sh` (no checksum step) | `CODE VERIFIED` | Direct comparison of both scripts' contents |
| Two-layer rollback exists: a fast kill-switch (disable the Platform Core auth path, Loady falls back to its own auth) and a full restore-from-backup path | `CODE VERIFIED` + `LOCAL LIVE-STACK VERIFIED` | `LOADY_ROLLBACK_PLAN.md`, `BILLING_ROLLBACK_RUNBOOK.md`, `PRODUCTION_ROLLBACK_REHEARSAL.md` |
| Real production rollback timing (how long a full restore actually takes against real data volume) | `PRODUCTION PREFLIGHT REQUIRED` for the baseline, `LIVE OBSERVATION ONLY` for a real rollback execution | N/A |

## 5. Capacity and resource planning

| Conclusion | Tier | Source |
|---|---|---|
| Platform Core's addition is estimated at 400-700 MB RAM (`PRODUCTION_CAPACITY_PLAN.md:29`) | `DOCUMENTED ONLY` (an estimate, not a measurement) | `PRODUCTION_CAPACITY_PLAN.md` |
| **Internal inconsistency found**: the same document also states "~500 MB-1 GB" for what reads as the same estimate at `PRODUCTION_CAPACITY_PLAN.md:54`, in the context of the VPS "running close to its 8 GB ceiling under Loady alone." These two numbers (400-700 MB vs 500 MB-1 GB) are not identical and are never reconciled in the source document. | Documented here as a genuine staleness finding, not silently fixed | `PRODUCTION_CAPACITY_PLAN.md` lines 29, 54 |
| **Threshold mismatch found**: `PRODUCTION_CAPACITY_PLAN.md:84-88` recommends preflight minimums of **1.5 GB free RAM** and **2 GB free disk**, while `scripts/platform/preflight-production-migration.sh`'s own hardcoded check requires **≥5 GiB free disk** (`df -Pk /`). The script is stricter than the plan's stated minimum, which is not unsafe, but the two numbers were never reconciled into one authoritative figure. | `CODE VERIFIED` (both numbers, as they actually appear) | `PRODUCTION_CAPACITY_PLAN.md` lines 84-88; `preflight-production-migration.sh` disk check |
| **Resolution for this mission**: Phase 5's resource budget and Phase 25's GO/NO-GO gate adopt the **stricter** of each pair (5 GiB disk, and RAM headroom computed from the higher 1 GB estimate, i.e. require ≥2 GB free RAM) as the single authoritative threshold, superseding both documents' own numbers going forward. | New decision, recorded here | This document |
| Actual current free RAM/disk/CPU on the real VPS | `PRODUCTION PREFLIGHT REQUIRED` | Explicit constraint restated by this mission |

## 6. Security review staleness

| Conclusion | Tier | Source |
|---|---|---|
| `MISSION_6_SECURITY_REVIEW.md:123` lists `OAuthClient.webhook_signing_secret` stored in plaintext as an open finding | `CODE VERIFIED` **as of the time that doc was written** — but stale now | `MISSION_6_SECURITY_REVIEW.md` line 123 |
| `MISSION_6_SECURITY_REVIEW_CONTINUATION.md:84` confirms this was fixed with AES-256-GCM encryption, fail-closed outside test/dev | `CODE VERIFIED` (current state) | `MISSION_6_SECURITY_REVIEW_CONTINUATION.md` line 84; confirmed by direct grep against current `platform-core/backend` source (see Phase 44 for the fresh re-check) |
| **Finding**: the original `MISSION_6_SECURITY_REVIEW.md` was never edited to mark this item closed, so a reader of that file alone would believe the plaintext-secret issue is still open. No prior mission produced an erratum. | Documented here; **not silently corrected in the original file** — that file is a historical record of a point-in-time review and rewriting it after the fact would itself be a form of the "never upgrade DOCUMENTED ONLY to VERIFIED" anti-pattern in reverse. The correction lives here and will be carried into Phase 44's fresh security review. | This document |
| `PRODUCTION_READINESS_CHECKLIST.md`'s BLOCKER #2 ("Ecosystem-wide logout does not exist") is self-flagged at line 389 of that same file as stale, since Mission 6 added `logout_all_sessions` (security_epoch-based) and Mission 7 closed the remaining single-session-revoke gap — but the checklist "was not otherwise re-audited" to confirm the rest of its BLOCKER list is current. | `DOCUMENTED ONLY` (self-flagged staleness, not independently re-verified until Phase 44) | `PRODUCTION_READINESS_CHECKLIST.md` lines 385-397 |
| Remaining genuinely-unstruck BLOCKER in that checklist: backup off-site storage still not configured anywhere; self-signed TLS in staging (not production — production TLS is addressed fresh in Phase 14) | `DOCUMENTED ONLY`, carried forward as real open items | Same file, "Consolidated summary" section |

## 7. Operator scripts (read in full this mission)

| Script | What it actually checks/does | Tier |
|---|---|---|
| `scripts/platform/preflight-production-migration.sh` | 9 numbered checks: git branch+clean tree, Docker daemon reachable, ≥5 GiB free disk, both backend containers `healthy` via `docker inspect`, both `/api/health`+`/ready` HTTP checks, signing key + token-encryption key present, Loady's platform-auth flag enabled, both services' Alembic at `(head)`, backup destination writable. Prints exactly `GO`/`NO-GO:` + reasons. | `CODE VERIFIED` (read in full); never run against anything beyond staging defaults | 
| `scripts/platform/verify-migration.sh` | Read-only reconciliation: total/linked user counts, linked-count == distinct-`global_user_id` invariant, Platform Core user/entitlement/payment_record counts (hard invariant: `payment_records` must be exactly 0 post-identity-migration, since billing cutover is a separate later stage), orphan check via set difference. Prints `RECONCILIATION: PASS`/`FAIL`. | `CODE VERIFIED` (read in full) |
| Both scripts' staging defaults are hardcoded (container names, ports 8090/8443, branch `unified-platform-v1`); production mode requires explicit `:?`-mandatory env vars for every value, with no silent fallback to a guessed production value | `CODE VERIFIED` — this is a genuine safety property worth preserving in Phase 18's consolidated read-only preflight script, not re-inventing | Both scripts |

## 8. Minor staleness inventory (non-blocking, recorded for completeness)

- `platform-core/compose.staging.yml:97` defaults `PLATFORM_STAGING_HTTP_PORT` to `8080`, while `platform-core/.env.staging.example:43` sets it to `8091`. Both values work (the `.env.staging.example` value wins when that file is actually used, per Compose's own env-file precedence), but the divergence means a reader of the compose file alone sees a different port than a reader of the example env file. **Staging-only; no production impact** (`compose.rc.yml`'s own port variables are separate and were read directly — `RC_HTTP_PORT`/`RC_HTTPS_PORT`, defaulting to 80/443 — and do not share this inconsistency).
- `scripts/restore-rehearsal.sh` (root) should be documented as superseded by `scripts/platform/verify-backup-restorable.sh` rather than silently left to confuse a future operator (addressed in Phase 52's operator command index, which will reference only the current script).
- No Cloudflare cache-purge/bypass procedure exists anywhere in prior mission docs for the maintenance-mode window. This is a genuine gap, not a contradiction — addressed as new content in Phase 13 (`CLOUDFLARE_CUTOVER_PLAN.md`) and Phase 21 (maintenance window), not as an application code change.
- **`LOADY_PRODUCTION_MIGRATION_PLAN.md` §1 (Mission 3-era) is stale in three places**, superseded by later missions but never updated: prerequisite #2 (a real production signing key) is now a documented, scripted procedure (`PRODUCTION_SECRET_BOOTSTRAP.md`); prerequisite #3 ("`platform_oidc_tokens.refresh_token` must be encrypted at rest... not yet implemented") **was implemented** — `token_encryption_service.py`'s AES-256-GCM encryption, confirmed live per `PRODUCTION_SECRET_INVENTORY.md`'s "verified live in phase 17" note; prerequisite #4 (a decision on synchronous entitlement-gate architecture) **was decided** — the hybrid cached/fail-closed resolver built across Missions 4-7 (`ENTITLEMENT_AVAILABILITY.md`, `platform_entitlement_service.py`, `/api/v1/capabilities/me`) is exactly that decision, implemented and tested. Not corrected in the original file, per the same "historical record, not silently rewritten" principle applied to the `MISSION_6_SECURITY_REVIEW.md` finding above — the correction lives here and in `PRODUCTION_DATA_MIGRATION_INPUTS.md` (Phase 17).

## 9. What this audit deliberately does not do

- It does not re-run the 1,131-test baseline (Platform Core 284 / Loady backend 660 / Loady frontend 187) — that re-run belongs to Phase 50 after all other phases' code/doc changes (if any) are known, so the final count reported there is the true final number, not a mid-mission snapshot.
- It does not fix the migration-re-run entitlement-overwrite defect (§2) or the plaintext-secret documentation staleness (§6) as code changes — neither is a "genuine production-readiness defect" requiring an application code change under this mission's no-feature-creep rule; both are handled as documentation/procedure (Phase 39's rollback point-of-no-return language, and this audit's own correction note respectively).
- It does not attempt to verify anything marked `PRODUCTION PREFLIGHT REQUIRED` or `LIVE OBSERVATION ONLY` — by definition, nothing available to this mission can close those tiers.
