# Loady Migration Dry-Run — what was actually run, and its results

This documents the real, local execution of the migration tooling this
mission built — not a plan. Every server, database, and HTTP request
described below ran on this machine against throwaway local data; nothing
touched production, and nothing was deployed anywhere.

## 1. The tooling

- `platform-core/backend/app/services/loady_migration_service.py` —
  `run_migration(platform_session, loady_engine, actor, reason, dry_run=True)`.
  Reads Loady's `users`/`subscriptions` tables via plain SQLAlchemy Core
  reflection (never imports Loady's ORM), two-phase (identity resolution,
  then memberships/roles/entitlements), and owns the commit/rollback
  decision for **both** the Platform Core session and the Loady
  connection itself — a caller cannot half-apply a dry run.
- `platform-core/backend/app/scripts/loady_migration_dry_run.py` — the
  CLI: `python -m app.scripts.loady_migration_dry_run --loady-database-url
  <url> [--commit] [--reason "..."]`. Refuses any URL containing the word
  "production" outright.
- `backend/alembic/versions/8a1e5c3f9b02_*.py` — adds the nullable, unique
  `users.global_user_id` column Loady persists the mapping in.

## 2. Unit-level proof: 12 synthetic fixtures

`platform-core/backend/tests/test_loady_migration.py` builds a temporary
SQLite database matching Loady's real audited schema
(`LOADY_MIGRATION_AUDIT.md`) and populates it with all 12 required
fixtures: free, paid Pro, paid Creator, gifted Pro, gifted Creator, admin,
email-unverified, disabled, has-history (see the live run below for the
real version of this one), multiple-downloads, existing-Paddle-reference,
and one deliberate collision/invalid case. Result: **11 of 12 migrate
correctly** (created), the 12th is correctly reported as `conflicted`
(an orphaned `global_user_id` pointing at no Platform Core row). Running
the whole batch **twice** in a row produces `created=0, skipped=11` on
the second run — proven idempotent. 6/6 tests pass
(`pytest tests/test_loady_migration.py`).

## 3. Live run: 4 real users through 2 real running servers

Platform Core (`:8100`) and Loady (`:8000`) were both started locally
against fresh temporary SQLite databases (`docs/platform/LOCAL_DEVELOPMENT.md`'s
own documented commands), Loady registered as a real OAuth client via
`register_loady_client.py`. Four real Loady accounts were created through
Loady's own real signup API:

| Loady account | Setup |
|---|---|
| `existing-mission3@example.com` | plain signup + one real history row inserted via `history_repo.upsert()` |
| `gifted-mission3@example.com` | signed up, then a real Loady admin called `PATCH /api/admin/users/{id}/subscription {"plan":"pro"}` — Loady's existing, unmodified gift-subscription endpoint |
| `disabled-mission3@example.com` | signed up, then disabled via `POST /api/admin/users/{id}/status {"status":"disabled"}` |
| `admin-mission3@example.com` | signed up, then promoted via Loady's own `promote_admin.py` |

### 3.1 Dry run first

```
python -m app.scripts.loady_migration_dry_run --loady-database-url sqlite:///.../commercial.db
=== DRY RUN (nothing was written - pass --commit to persist) ===
created=4 linked=0 skipped=0 conflicted=0 failed=0
```

Confirmed **zero writes** on the Loady side by re-querying
`SELECT email, global_user_id FROM users` directly afterward — all four
rows still showed `global_user_id = NULL`.

### 3.2 Committed run

```
=== COMMITTED ===
created=4 linked=0 skipped=0 conflicted=0 failed=0
-- CREATED --
  existing-mission3@example.com  -> usr_d9acc68a7f384b36915e259d8cbab69c  (free)
  gifted-mission3@example.com    -> usr_c197c5bab8a14108b1916eaac84ec6fb  (gifted, pro)
  disabled-mission3@example.com  -> usr_f750add58cc74e3db956f7ad9aa020cd  (free)
  admin-mission3@example.com     -> usr_e80b79f8f709408e9a8f3539c7a8fb84  (free)
```

Verified directly against Platform Core's own SQLite file:

- Exactly 4 `users` rows for these emails — no duplicates.
- `admin-mission3@example.com`'s `role_assignments` row is
  `(role_slug='admin', scope='product:loady')` — **not** `scope='global'`.
- `entitlements`: `gifted-mission3` shows `source='gifted'`; the other
  three show `source='free'`.
- **`payment_records` table: 0 rows, total.** The gifted grant produced no
  fabricated revenue of any kind.
- `disabled-mission3@example.com`'s Platform Core `status` column reads
  `disabled` — copied faithfully from Loady's own status.

### 3.3 Idempotency: run it again

```
python -m app.scripts.loady_migration_dry_run --loady-database-url ... --commit
=== COMMITTED ===
created=0 linked=0 skipped=4 conflicted=0 failed=0
```

Same 4 `global_user_id` values as before — nothing duplicated, nothing
re-created, nothing changed.

## 4. Dormant-by-default, verified

```
curl http://localhost:8000/api/auth/platform/status   # before configuring
{"enabled": false}
curl http://localhost:8000/api/auth/platform/login
404 Not Found
```

Then, after exporting `PLATFORM_CLIENT_ID`/`PLATFORM_CLIENT_SECRET`
(printed by `register_loady_client.py`) and restarting Loady's backend
only (no code change, no redeploy):

```
{"enabled": true}
```

## 5. Live acceptance tests (real HTTP, real cookies, no mocks)

A cookie-jar HTTP client drove the exact same request sequence a real
browser would, against the two live servers above (script:
`e2e_check.py`, run from this session's scratch directory). Full output,
one clean run, no failures:

```
=== 1. EXISTING LOADY USER - password + linking + history ===
  central login OK, landed on /dashboard
  /api/account: {'email': 'existing-mission3@example.com', 'plan': 'free', 'provider': 'none'}
  history titles visible after central login: ['Mission 3 migration-dry-run proof download download']
  PASS: existing user's password worked centrally, session established, history preserved.

=== 2. STEADY-STATE RE-LOGIN - matches by global_user_id, not email ===
  PASS: second central login resolves the same account again.

=== 3. GIFTED LOADY ACCESS - identical capabilities, no Paddle op, no payment record ===
  /api/account: {'plan': 'pro', 'provider': 'gifted'}
  PASS: gifted user authenticates centrally with the identical Pro capabilities, provider=gifted,
        and Loady's own Paddle-only billing history correctly refuses to fabricate a Paddle record
        (404 'No billing subscription found').

=== 4. CROSS-PRODUCT SSO - same central session reaches Demo Product A with NO second password entry ===
  Demo Product A landing page reached with ZERO extra password prompts.
  Demo Product A shows 'No active entitlement' - Loady's gifted/pro plan does NOT leak across products.
  Loady account email: existing-mission3@example.com | Demo-A shows global id: usr_d9acc68a7f384b36915e259d8cbab69c
  PASS.

=== 5. DISABLED USER - central login must fail outright ===
  central login correctly rejected: status=403 {'code': 'ACCOUNT_DISABLED', ...}
  PASS.

===== SUMMARY =====
ALL ACCEPTANCE CHECKS PASSED
```

This is the single strongest piece of evidence in this mission: it proves,
end to end and without mocks, that (a) an existing Loady user's real
Argon2id password verifies correctly against Platform Core after
migration — the hash-compatibility claim, exercised for real; (b) the
same account is resolved on a second login with no duplication; (c) a
gifted grant behaves identically to a paid Pro plan with zero Paddle
interaction; (d) one central login reaches a second, independent product
with no further password prompt and no entitlement leakage; and (e) a
centrally-disabled account cannot obtain any new session anywhere.

A genuine, useful side-effect of this live run: Platform Core's existing
login rate limiter correctly throttled repeated login attempts against
the same test account (`429 Too Many Requests`) during iterative testing
— an existing protection, working as intended, not a defect.

## 6. Cleanup

All three local test servers (Platform Core `:8100`, Loady `:8000`, Demo
Product A `:9301`) were stopped at the end of this mission. Their
databases lived entirely under this session's scratch directory and were
never pointed at any file inside `local-media-downloader/backend/data/`
or any other path Loady's real local instance uses.
