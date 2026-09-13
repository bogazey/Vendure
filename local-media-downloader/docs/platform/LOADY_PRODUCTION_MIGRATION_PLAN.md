# Loady → Platform Core: Production Migration Plan

**Nothing in this document has been executed against production.** This
is the plan for a future, separate, deliberately-approved effort, built
on top of what this mission actually implemented and verified locally
(`LOADY_MIGRATION_DRY_RUN.md`) rather than on assumptions. See
`LOADY_MIGRATION.md` for the original (mission 2) planning-only version
this supersedes with real, tested detail.

## 1. Prerequisites before this can even be attempted

1. **Platform Core must be a real, deployed, monitored service** —
   production Postgres (not SQLite), a real TLS-terminated
   `PLATFORM_AUTH_BASE_URL`, its own on-call/monitoring, and its own
   backup strategy. None of this exists yet; this mission's Platform Core
   only ever ran as a local dev process.
2. **A real production JWT signing key**, provisioned out of band (not
   the first-run auto-generated dev key — see
   `platform-core/backend/app/security/jwt_keys.py`'s own docstring).
3. **`platform_oidc_tokens.refresh_token` must be encrypted at rest**
   before any real user's refresh token is stored there — flagged as a
   TODO directly in `commercial_models.py`'s `PlatformOidcToken`
   docstring, not yet implemented (this mission's local dry run used only
   throwaway synthetic tokens, so this gap was acceptable for that
   purpose but is not acceptable for real user data).
4. **A decision on the entitlement-gate architecture question** left open
   in `LOADY_IDENTITY_INTEGRATION.md` §5: whether Loady's live download
   gate ever calls Platform Core synchronously, and if so, what happens
   when Platform Core is briefly unreachable. This mission deliberately
   did not decide this — `platform_entitlement_service` exists as a
   capability precisely so this decision can be made later without
   rebuilding anything.
5. **A real communication plan for the one-time re-login** every existing
   Loady user will need (see §4) — support documentation, an in-product
   banner, and a defined migration window.

## 2. Staged rollout (never a single flag flip for the whole user base)

1. **Stage 0 — already done, this mission**: build and prove the
   mechanism locally, dormant in production
   (`PLATFORM_CLIENT_ID` unset — see `LOADY_ROLLBACK_PLAN.md` §1).
2. **Stage 1 — internal/staff accounts only.** Configure
   `PLATFORM_CLIENT_ID` in a staging environment against a **staging**
   Platform Core instance (never production data), run the migration
   script there, and have the team itself use "Sign in with Central
   Identity" for a real week or two before any real customer sees it.
3. **Stage 2 — dry-run against a real, read-only production database
   copy.** Run `loady_migration_dry_run.py` (no `--commit`) against a
   restored snapshot of the real production `commercial.db`/Postgres —
   never the live database directly — and manually review the full
   `created`/`linked`/`skipped`/`conflicted`/`failed` report for
   anything unexpected (a `conflicted` count above zero on real data
   means stop and investigate before going further, not "run it anyway").
4. **Stage 3 — the real commit run, during a defined low-traffic
   window**, against the real production database, with
   `PLATFORM_CLIENT_ID` still **unset** in production at that moment (the
   migration script only needs read+write DB access, not a live OIDC
   flow — see `run_migration`'s signature, it takes a `loady_engine`
   directly, it never goes through HTTP).
5. **Stage 4 — enable the integration** (set `PLATFORM_CLIENT_ID`/
   `SECRET` in production) once Stage 3's report has been reviewed and
   confirms `failed=0` and `conflicted=0` for the full user base — or with
   every `conflicted` row individually resolved first.
6. **Stage 5 — monitor.** Watch Platform Core's `audit_logs` (every
   import is recorded as `AuditAction.LOADY_MIGRATION_IMPORT`) and Loady's
   own error logs for the first real login wave; keep §1's kill switch
   ready and rehearsed.

## 3. What existing users experience (from `LOADY_MIGRATION.md`, confirmed unchanged by this mission's actual build)

- **One re-login, not a password reset.** The very first login after
  migration is through Platform Core's own login form, using the **same
  email and password they already have** — proven live in this mission
  (`LOADY_MIGRATION_DRY_RUN.md` §5, item 1: an existing Loady password
  verified successfully against Platform Core with zero code path
  changes to the password itself).
- **Download history, plan, and gifted status are all unaffected** — none
  of them are rewritten by the migration; `global_user_id` is a side
  column only.
- **Existing sessions are not force-terminated.** A user with the app
  already open keeps working until their current session's natural
  expiry, at which point their next login goes through the new flow.

## 4. Rollback readiness

Every step above must be executed with `LOADY_ROLLBACK_PLAN.md` open and
rehearsed beforehand — specifically §1 (instant kill switch) and §3
(Alembic downgrade), both verified working in this mission's local
testing.

## 5. Explicit non-goals for the first production migration

- **Do not** wire `platform_entitlement_service` into the live download
  gate as part of this migration — that is a separate, later decision
  (§1.4).
- **Do not** attempt an ecosystem-wide "sign out everywhere" as part of
  this migration — it does not exist (`LOADY_IDENTITY_INTEGRATION.md`
  §6) and building it is out of scope here.
- **Do not** delete or stop populating Loady's own `password_hash`,
  `email_verified`, or `status` columns after migration — Loady's local
  login must remain a fully working fallback indefinitely, not just
  during a transition window, unless a much later, separate decision
  deprecates it.
- **Do not** move Paddle customer/subscription identifiers into Platform
  Core at any stage — they stay in Loady's own database permanently, by
  design (`LOADY_MIGRATION.md` §3).

## 6. Recommendation

See the mission's final report for the explicit overall readiness
recommendation. In short: the **mechanism** is built, tested, and proven
to work correctly end-to-end against real (if synthetic) data and real
running services; the **production environment and operational
prerequisites** in §1 are not yet in place. Those two facts are
independent, and this document exists so the second one is never confused
with the first.
