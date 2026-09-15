# Rollback Triggers and Point of No Return (Mission 15, Phases 37 & 39)

## Objective rollback triggers (Phase 37) — decided in advance, not judgment calls made under pressure

Roll back immediately (per `FINAL_PRODUCTION_ROLLBACK_RUNBOOK.md`) — no
further debugging in production first — if any of the following is
observed:

| Trigger | Threshold | Source |
|---|---|---|
| Migration conflict outside the expected set | Any `conflicted`/`failed` row in the MIGRATION COMMIT step not already seen and accepted in the MIGRATION DRY RUN step | `FINAL_MIGRATION_DRY_RUN_PROCEDURE.md` |
| Reconciliation mismatch | `RECONCILIATION: FAIL` from `verify-migration.sh` on any invariant | `RECONCILIATION_PACKAGE.md` |
| History/usage ownership mismatch | Any migrated user's download history or usage totals visibly wrong post-migration | Direct consequence of the migration touching only `global_user_id`, never history rows — any mismatch means something unexpected happened |
| Login systemic failure | More than an isolated one-off login failure across the SSO test + real traffic in the observation window | `FINAL_PRODUCTION_CUTOVER_RUNBOOK.md` SSO TEST step |
| Platform Core instability | Repeated container restarts, crash loops, or health check flapping post-cutover | `SINGLE_VPS_FAILURE_DOMAIN_REVIEW.md` |
| Database corruption | Any integrity-check failure on either Postgres instance | N/A — self-evident |
| Signing-key failure | JWKS mismatch, token verification failures across multiple users | `KEY_ROTATION_RUNBOOK.md`'s own failure mode description |
| Token-encryption failure | `PlatformOidcToken` rows failing to decrypt | `PRODUCTION_SECRET_INVENTORY.md`'s documented failure mode for a missing/wrong key |
| Entitlement escalation | Any user's entitlement is *more* permissive post-migration than pre-migration without an explicit, deliberate grant | `ENTITLEMENT_VALIDATION_PACKAGE.md` |
| Paid-user entitlement loss | Any Paddle-paid or gifted user loses entitlement they held pre-migration | `ENTITLEMENT_VALIDATION_PACKAGE.md`; this is the one direction rollback is specifically designed to always catch, per `PRODUCTION_ROLLBACK_REHEARSAL.md`'s "any entitlement change should fail toward disappearing, never appearing" principle |
| Download authorization systemic failure | Downloads blocked for users who should be entitled, across more than an isolated account | `DOWNLOAD_VALIDATION_PACKAGE.md` |
| Unexpected Paddle mutation | Any change to a Paddle subscription/customer record this migration should never touch (identity migration never calls Paddle at all — any such mutation observed is evidence something is badly wrong, not migration-caused, but still a stop-everything signal) | `PADDLE_LIVE_INPUTS_REQUIRED.md` — identity migration has zero Paddle interaction by design |
| Grand Admin critical authorization failure | Admin auth broken, or Grand Admin showing incorrect product/entitlement data for a known test account, in a way that indicates a systemic authorization bug rather than an isolated display glitch | `GRAND_ADMIN_VALIDATION_PACKAGE.md` |

## Non-triggers (investigate, don't roll back)

- Platform Core briefly unreachable while Loady's cache still serves
  (bounded by `ENTITLEMENT_CACHE_TTL_MINUTES`) — `PRODUCTION_ROLLBACK_REHEARSAL.md`
  finding C, measured live.
- A single isolated login failure with an identifiable, non-systemic cause
  (e.g. a user's own network issue).
- Billing page cosmetic issues that don't indicate a systemic break (see
  BILLING TEST step's own stop condition distinction).

## Point of no return (Phase 39)

**The MIGRATION COMMIT step is the threshold.** Before it: every prior
step (backup, dry run, GO/NO-GO) is either read-only or trivially
reversible (maintenance mode itself). After it: rollback means restoring
from the FINAL BACKUP artifact, not simply reverting a flag — a
meaningfully more involved, ~10-20-minute operation
(`FINAL_PRODUCTION_ROLLBACK_RUNBOOK.md`'s recovery-time estimate) rather
than a 5-second kill switch.

**What makes rollback progressively harder the longer the window since
commit** (Phase 39's explicit concern):

1. **New billing writes** — not applicable to this identity-only cutover
   (Loady's Paddle integration is architecturally untouched); would matter
   for the *separate* billing cutover, where `BILLING_ROLLBACK_RUNBOOK.md`
   has its own equivalent analysis.
2. **New central-only identities** — any brand-new signup that goes
   through central SSO *after* `PLATFORM_CLIENT_ID` is turned on (Stage 4
   of `LOADY_PRODUCTION_MIGRATION_PLAN.md`) exists only via Platform
   Core's own user table; rolling back Loady's database does not delete
   that Platform Core account, but it does mean Loady no longer recognizes
   it as linked. **This is why the observation-period policy below exists.**
3. **Post-migration Grand Admin account changes** — the entitlement
   asymmetry documented in `FINAL_PRODUCTION_ROLLBACK_RUNBOOK.md`'s "one
   thing a rollback does NOT undo" section.
4. **New subscription mutations** — same reasoning as #1, not applicable
   to this cutover specifically.

## How the initial observation period minimizes divergent writes

The recommended policy for the first observation window (the 15-min/1-hr
slices of `POST_MIGRATION_MONITORING.md`, and arguably through the 24-hr
mark): **avoid deliberately exercising Grand Admin gift/entitlement
actions on migrated accounts**, and treat any *new* signup during this
window as a known, accepted, one-way commitment (rolling back would
orphan it, not delete it — an acceptable, bounded, and explicitly known
cost, not a silent one). This is a process policy, not a technical
restriction — there is no code-level lock preventing these actions, and
building one would be exactly the kind of speculative complexity the No
Feature Creep rule guards against for a risk that a documented operational
policy already manages adequately.
