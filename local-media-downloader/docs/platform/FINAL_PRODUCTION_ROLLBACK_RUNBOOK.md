# Final Production Rollback Runbook (Mission 15, Phase 38)

**Nothing in this document has been executed.** Consolidates
`LOADY_ROLLBACK_PLAN.md`, `BILLING_ROLLBACK_RUNBOOK.md`,
`scripts/platform/rollback-platform-migration.sh`, and
`PRODUCTION_ROLLBACK_REHEARSAL.md`'s measured timings into one executable
runbook for the identity-migration cutover
(`FINAL_PRODUCTION_CUTOVER_RUNBOOK.md`). It does not re-derive the
mechanism — every layer below cites the document/script that already
built and, where noted, measured it.

**Mission 16 update**: `scripts/platform/platform-production.sh rollback`
(see `PRODUCTION_CONTROLLER.md`, `PRODUCTION_CONTROLLER_RECOVERY.md`)
now wraps the decision-and-execute sequence below with persisted state
(so `rollback-plan` can show exactly what a rollback would restore,
using the deployment's own recorded backup ID) and two-stage deliberate
confirmation (`--confirm 'ROLLBACK <id>'`, plus `--confirm-restore
'RESTORE-DATABASE <id>'` when a database restore is required) — this is
the **preferred** way to actually run a rollback. The layer-by-layer
detail below remains the authoritative explanation of what each layer
does and when to choose it; use it directly if the controller is ever
unavailable.

## Decision point: which layer

| Symptom | Layer | Why |
|---|---|---|
| Platform Core briefly unreachable, Loady's hybrid cache still serving | **No rollback** — wait out the cache TTL (≤15 min, `ENTITLEMENT_CACHE_TTL_MINUTES`) | `PRODUCTION_ROLLBACK_REHEARSAL.md` finding C: measured live, no action needed for a short outage |
| The Platform-Core-auth integration itself is misbehaving (wrong redirect, bad token, login errors), but Loady's own database is untouched | **Layer 1 — kill switch** | `scripts/platform/rollback-platform-migration.sh --layer kill-switch`: unset `PLATFORM_CLIENT_ID`/`SECRET`, restart Loady's backend. Measured: **5 seconds**. No deploy, no data change — Loady's local login, entirely unmodified by this mission, resumes immediately for every account, migrated or not. |
| A single account was linked incorrectly (support case, wrong email match) | **Targeted unlink** | `UPDATE users SET global_user_id = NULL WHERE id = '<id>';` — safe, reversible, does not touch password/status/history. Re-links by email on next central login. |
| The migration commit itself produced wrong/unexpected data (reconciliation FAIL, systemic login failure, entitlement escalation, or any other objective trigger below) | **Layer 2 — full restore** | `scripts/platform/rollback-platform-migration.sh --layer full-restore --backup-dir <dir>`: restores Loady's Postgres from the FINAL BACKUP step's artifact. Measured (staging, 54 users): kill-switch 5s + DB restore 51s + container switch 14s + validation 40s = **110s (~1 min 50s) total**, not counting backup retrieval time. |
| Database migration itself (Alembic) needs undoing | **Alembic downgrade** | Both new Loady migrations (`global_user_id`, related columns) have a real, tested `downgrade()` — see `LOADY_ROLLBACK_PLAN.md` §3. Prefer the full-restore path above for a real incident; Alembic downgrade is the mechanism proof, not the recommended first response, per that document's own guidance not to assume downgrade is always safer than backup restore. |

## Step-by-step (full restore — the deepest layer, others are strict subsets)

1. **Decide** — using the table above; do not restore blindly if the
   kill switch alone resolves the symptom.
2. **Stop new writes** — maintenance mode should already be on if this is
   happening inside the cutover window; if the problem surfaces later
   (post-window), re-enable it first.
3. **Kill switch first, always** — even when heading to full restore,
   flip `PLATFORM_CLIENT_ID` off immediately; this alone stops any further
   central-auth-driven writes while the restore proceeds.
4. **Restore**:
   ```bash
   BACKUP_ENCRYPTION_PASSPHRASE=<PLACEHOLDER> \
     scripts/platform/rollback-platform-migration.sh --env production \
     --layer full-restore --backup-dir <FINAL-BACKUP-run-dir> --env-file <loady-env-file>
   ```
5. **Verify** — two logins (a never-migrated account and a migrated one),
   one download, and the same record-count queries
   `verify-migration.sh` already runs, confirming they now match the
   **pre-migration** counts, not the post-migration ones.
6. **Lift maintenance mode.**
7. **Post-incident**: write up what triggered the rollback before doing
   anything else — this is the input to the next attempt's fix, not
   optional cleanup.

## The one thing a rollback does NOT undo — stated plainly, not buried

**Any entitlement change made exclusively through Grand Admin after the
migration commit is not preserved by a rollback to the pre-Platform-Core
architecture.** `PRODUCTION_ROLLBACK_REHEARSAL.md`'s own finding: restoring
Loady's database to its pre-migration state has no way to also un-apply a
gift grant/revoke that only ever existed in Platform Core's database
(which is *not* restored by this procedure — only Loady's database is).
**Practical consequence for the observation-period policy
(`PRODUCTION_DEPLOYMENT_SEQUENCING.md` Phase 23 / Phase 39 below)**: avoid
Grand Admin entitlement actions on migrated accounts during the initial
observation window specifically because they would create exactly this
asymmetry if a rollback became necessary afterward.

## Billing rollback (only relevant if billing cutover was also in scope — see `BILLING_ROLLBACK_RUNBOOK.md`)

Not part of the identity-only cutover this runbook otherwise describes —
`BILLING_CUTOVER_RUNBOOK.md`'s Stage 5 (cutting Loady's own webhook
endpoint over) is a separate, later, independently-authorized action with
its own rollback runbook already written. Do not conflate the two: rolling
back identity migration does not require touching Paddle's webhook
destinations at all.

## Recovery time estimate (Phase 40)

**Measured** (staging, 54 synthetic users, backup already on local disk):
110 seconds mechanical restore time. **Not measured** (production scale):
the dominant unknown for a real incident is backup **retrieval** time
(off-server storage is a documented, still-open gap —
`PRODUCTION_BACKUP_PACKAGE.md`), not the restore mechanics, which scale
with database size and will take longer than 51 seconds for a real
production `pg_restore`. **Planning estimate: 10-20 minutes total**,
dominated by backup retrieval and human decision time — this is
`PRODUCTION_REHEARSAL_PLAN.md`'s own prior estimate, re-confirmed here,
not a new number invented by this mission. Exact real-world timing remains
`PRODUCTION PREFLIGHT REQUIRED` until measured against real data volume.
