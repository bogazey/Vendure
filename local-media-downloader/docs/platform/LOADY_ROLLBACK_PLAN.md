# Loady Migration Rollback Plan

Every layer this mission touched has an independent, low-risk way back.
They are listed from fastest/safest to most involved — a real incident
would normally only ever need the first one.

## 1. Instant kill switch: unset the Platform config (no deploy, no code change)

`platform_identity_service.is_configured()` is `bool(PLATFORM_CLIENT_ID
and PLATFORM_CLIENT_SECRET)`. Clearing either variable (or simply never
setting them, the shipped default) makes
`routes_platform_auth.py`'s `/login` and `/callback` 404 immediately, on
the very next request — no restart-order dependency, no partial state.
Loady's own signup/login/password-reset/email-verification, which this
mission never modified, are completely unaffected and were never touched
by this switch. This is the correct response to almost any problem
discovered with the integration itself.

Users who already linked a `global_user_id` and go back to using
Loady's local login are unaffected — `global_user_id` is a side column,
never consulted by Loady's own password-login path
(`auth_service.login`), which still works exactly as it did before this
mission for every account.

## 2. Unlink a specific account

To fully undo the link for one user (e.g. they linked the wrong central
identity by mistake, or a support case requires it):

```sql
UPDATE users SET global_user_id = NULL WHERE id = '<loady-user-id>';
```

This is safe and reversible: it does not touch `password_hash`,
`status`, `email_verified`, or any subscription/history row. The next
time that account logs in centrally, `_find_or_link_local_user` will
re-link it by email (since `global_user_id` is NULL again) rather than
create a duplicate — see `LOADY_IDENTITY_INTEGRATION.md` §4.

On the Platform Core side, nothing needs to change: the `Entitlement`,
`ProductMembership`, and `RoleAssignment` rows for that `global_user_id`
simply become unreferenced by Loady until re-linked; they do not need to
be deleted, since Platform Core's own `products`/`entitlements` tables
have no foreign key back into Loady's database at all (by design — see
`LOADY_MIGRATION.md`'s database-boundary section).

## 3. Database rollback (Alembic downgrade)

Both new Loady migrations are purely additive and both have a real,
tested `downgrade()`:

```bash
cd local-media-downloader/backend
python -m alembic downgrade 7d2e9a4c1f83   # drops platform_oidc_tokens AND users.global_user_id
```

Verified this mission on both a fresh database and one with existing user
rows: `upgrade head` → `downgrade 7d2e9a4c1f83` → `upgrade head` again,
clean each time, no data loss to any pre-existing column. Dropping
`global_user_id` does **not** touch `history`, `usage_periods`,
`usage_events`, `analytics_events`, or `subscriptions` — none of them
reference it (`LOADY_MIGRATION_AUDIT.md` §§14-19).

`platform_oidc_tokens` (the OIDC access/refresh token cache) can also be
dropped on its own, independent of `global_user_id`, if only the token
cache needs clearing without fully disabling the integration:

```bash
python -m alembic downgrade 8a1e5c3f9b02   # drops only platform_oidc_tokens
```

## 4. Undoing a migration commit run entirely

If a real (`--commit`) migration run needs to be fully reversed on the
Loady side (e.g. it ran against the wrong database by operator error):

```sql
UPDATE users SET global_user_id = NULL;   -- or WHERE id IN (...) for a subset
```

This is the only Loady-side state the migration ever writes. On the
Platform Core side, the created `User`/`ProductMembership`/`Entitlement`/
`RoleAssignment`/`audit_logs` rows are left in place rather than deleted —
deleting user accounts is not a capability this mission builds (Platform
Core has no user-delete endpoint at all today), and leaving orphaned
Platform Core accounts around is harmless: they simply won't be reachable
from Loady anymore once `global_user_id` is cleared, and Platform Core's
own `audit_logs` retains the accurate record of what was imported and
when (`AuditAction.LOADY_MIGRATION_IMPORT`), which is exactly what you
want during an incident review.

## 5. What never needs rolling back

- **Loady's own auth system** — untouched, always available, never
  gated behind this integration in any way.
- **Paddle billing** — this mission made zero Paddle API calls and never
  wrote to `Subscription.provider_customer_id`/`provider_subscription_id`;
  there is nothing Paddle-side to undo.
- **Existing local Loady sessions** — a session issued before any
  rollback step above stays valid until its own natural expiry; none of
  the steps above force-invalidate a live session (Loady has no
  centralized session-revocation mechanism to do so, before or after this
  mission — see `LOADY_IDENTITY_INTEGRATION.md` §7).

## 6. Order of operations for a real incident

1. Unset `PLATFORM_CLIENT_ID` (§1) — stops the bleeding immediately,
   zero risk, zero data change.
2. Investigate using Platform Core's `audit_logs`
   (`AuditAction.LOADY_MIGRATION_IMPORT` entries carry
   `loady_user_id`/`global_user_id`/`entitlement_source`/`plan` for every
   row ever imported) plus Loady's own logs.
3. Only if specific accounts are actually wrong, unlink them individually
   (§2) — never a bulk `global_user_id` wipe unless the whole run was
   confirmed bad.
4. Alembic downgrade (§3) only if the schema itself needs to come out —
   this is the most invasive step and the last one to reach for.
