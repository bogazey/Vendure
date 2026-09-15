# Production Deployment Sequencing (Mission 15, Phases 22-23)

## Phase 22: Platform Core deployed and verified BEFORE any Loady identity migration

Ordered sequence — each step's checks are safe to perform without
affecting current Loady users, because Platform Core is not yet
authoritative for anything Loady does until the (separate, later)
migration step:

1. **Bring up the combined stack** (`compose.rc.yml`, real production
   secrets per `PRODUCTION_SECRET_BOOTSTRAP.md`/`PRODUCTION_SECRET_STORAGE_PLAN.md`)
   with `PLATFORM_CLIENT_ID` still **unset** in Loady's own environment.
   Loady's platform-auth integration is dormant by design when this is
   unset (`MISSION_7_ARCHITECTURE_AUDIT.md` §1) — every route in
   `routes_platform_auth.py` 404s cleanly, so Loady's existing users are
   completely unaffected by Platform Core's mere presence on the box.
2. **Health**: `GET https://id.<domain>/health` and `/ready` both return
   200; `/ready`'s JSON reports `signing_key: true` (confirms the RS256
   key mounted correctly) — exactly the two checks
   `preflight-production-migration.sh` already performs.
3. **Database**: `platform-core-postgres` container healthy;
   `platform-core-backend`'s `alembic current` shows `(head)`.
4. **Signing**: fetch `https://id.<domain>/.well-known/jwks.json`, confirm
   it returns the expected `kid` (`JWT_KEY_ID`) with a valid RSA public
   key — this is the one check that proves the *right* key file was
   mounted, not just *a* key file.
5. **Encryption**: confirm `PLATFORM_TOKEN_ENCRYPTION_KEY` is set on the
   Loady backend container (`docker exec ... printenv` for presence only,
   **never** print the value) — this is checked today by
   `preflight-production-migration.sh` already, via a var-presence check,
   not a value dump.
6. **Admin**: log into Grand Admin (`https://admin.<domain>`) with a
   freshly bootstrapped admin account (see `PRODUCTION_SECRET_BOOTSTRAP.md`
   #3's registration-script pattern) and confirm the dashboard loads and
   the product registry shows Loady already registered as a client (it
   must be — Loady's own `PLATFORM_CLIENT_ID`, even while unset in Loady's
   *own* config for dormancy, corresponds to a client record that was
   registered against Platform Core ahead of time via
   `register_loady_client.py`, independent of whether Loady's own env
   currently uses it).
7. **OAuth client**: confirm the registered Loady OAuth client's
   `redirect_uri` matches Loady's real production callback URL exactly —
   a mismatch here would only surface once `PLATFORM_CLIENT_ID` is
   actually turned on (step 9 below), so verifying it now, while nothing
   depends on it yet, avoids discovering the mismatch during the
   maintenance window.
8. **Only after all of 2-7 pass**: proceed to the maintenance window
   (`MAINTENANCE_WINDOW_PLAN.md`) and the identity migration itself.
9. **Turning on the integration** (`PLATFORM_CLIENT_ID`/`SECRET` actually
   set in Loady's production env) happens at Stage 4 of
   `LOADY_PRODUCTION_MIGRATION_PLAN.md` — **after** the migration commit
   (step H of the existing cutover runbook), not before, and not as part
   of this deployment-sequencing phase.

## Phase 23: shadow / non-disruptive validation — what this architecture actually supports

**No dual-write or shadow-traffic mechanism exists in this codebase.**
Confirmed by reading `platform_entitlement_service.py` and
`routes_platform_auth.py`: there is no code path that sends a *copy* of a
Loady request to Platform Core for comparison while still trusting only
Loady's own answer. The only "non-disruptive while not yet authoritative"
capability that genuinely exists is the one already described in step 1
above: **Platform Core can run, be fully deployed, and be fully verified
on the production VPS while `PLATFORM_CLIENT_ID` stays unset**, at which
point it is inert from Loady's perspective — not shadow-validated against
real traffic, simply not yet wired in at all.

This mission does **not** invent a shadow/dual-write mechanism to satisfy
Phase 23 more fully than the architecture already allows — building one
would be exactly the kind of speculative infrastructure addition the "No
Feature Creep" rule forbids, for a validation need steps 2-7 above already
cover through direct, targeted health/config checks rather than live
traffic comparison. The billing side has a real parallel-verification
period (`BILLING_CUTOVER_RUNBOOK.md` Stage 4's 7-day dual-webhook window)
precisely because *that* mechanism (Paddle sending the same event to two
registered destinations) already exists natively in Paddle's own webhook
model — identity/SSO has no equivalent native mechanism to piggyback on,
which is exactly why this phase's answer is "verify thoroughly before
activation" rather than "compare shadow traffic."

## What Phase 22/23 together establish for the final cutover runbook (Phase 26)

The maintenance window (`MAINTENANCE_WINDOW_PLAN.md`) starts only after
Platform Core has already passed every check above, days or hours earlier
if desired — deployment and verification carry **zero** time pressure,
unlike the migration commit itself. This is the single most valuable
practical consequence of this sequencing: nearly every hard-to-fix problem
(wrong signing key, wrong redirect URI, unreachable database) gets found
and fixed *before* the clock starts, not during it.
