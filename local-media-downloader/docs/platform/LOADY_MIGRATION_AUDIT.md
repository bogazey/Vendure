# Loady Migration Audit (code-verified, read before any implementation)

Every finding below cites an actual file:line in `local-media-downloader/
backend` as it exists on this branch — nothing here is inferred or
assumed. This supersedes the shorter, plan-only audit table in
`ARCHITECTURE.md` §1 with the full depth this mission requires.

## 1. User model/schema

`app/database/commercial_models.py:37-54`, table `users`:

| Column | Type | Notes |
|---|---|---|
| `id` | `String(36)`, PK | UUID4 string, `_uuid()` default |
| `email` | `String(320)`, unique, indexed | the only unique key |
| `password_hash` | `String(255)` | Argon2id, see §3 |
| `email_verified` | `Boolean` | default `False` |
| `created_at`/`updated_at` | `UTCDateTime` | |
| `status` | `String(20)` | `"active"`/`"disabled"` |
| `role` | `String(20)` | `"user"`/`"admin"` — see §12 |

No `global_user_id` column exists yet — added by this mission's migration
(§ below, `LOADY_MIGRATION_DRY_RUN.md`).

## 2. Authentication flow (overview)

Stateless-JWT access token (15 min, cookie) + opaque hashed, rotating
refresh token (30 days, cookie) — see §6/§7. `app/services/auth_service.py`
is the single service every auth-adjacent route calls through.

## 3. Signup flow

`auth_service.py:55-77`: normalize email, reject if `User` with that email
exists (`EmailAlreadyRegisteredError`), create `User` with
`security_service.hash_password(password)`, `email_verified=False`,
`role="user"`, issue a verification email token (§9), issue a session with
`remember_me=True` (signup has no remember-me choice — always persistent).
Endpoint: `POST /api/auth/signup` (`routes_auth.py:75-92`), rate-limited
10/hour/IP.

## 4. Login flow

`auth_service.py:79-98`: normalize email, look up user, **always run the
hasher** even for a missing user (`security_service.hash_password
("placeholder-timing-guard")` as the comparand) so "no such account" and
"wrong password" take identical time — a real anti-enumeration measure,
not incidental. Rejects disabled accounts (`AccountDisabledError`) after
password verification succeeds (so account existence still isn't leaked by
which error fires first for a correct password). `needs_rehash()` checked
and applied silently on success. Endpoint: `POST /api/auth/login`
(`routes_auth.py:95-102`), rate-limited 10/5min per IP+email.

## 5. Logout flow

`auth_service.py:123-131`: revokes exactly the presented refresh token
(sets `revoked_at`), no-ops on a missing/absent cookie. `POST /api/auth/
logout` (`routes_auth.py:105-112`) always clears both cookies regardless.

## 6. Access token / cookie behavior

JWT, `HS256`, secret from `settings.secret_key` (env `SECRET_KEY`, else a
random value generated once per process — sessions don't survive a
restart without a configured secret, by design, see
`commercial_settings.py:111-116`). Claims (`security_service.py:48-59`):
`sub` (user id), `role`, `type="access"`, `iat`, `exp` (+15 min), `jti`.
Cookie `lmd_access`, httpOnly, `SameSite=Lax`, `Secure` in production
(`COOKIE_SECURE`), path `/`. **`remember_me` controls whether the cookie
gets a `Max-Age` at all** (`routes_auth.py:44-46`):
```python
access_max_age = settings.access_token_ttl_minutes * 60 if result.remember_me else None
refresh_max_age = settings.refresh_token_ttl_days * 24 * 3600 if result.remember_me else None
```
`remember_me=False` → no `Max-Age` → a true browser-session cookie
(cleared when the browser itself closes, not on refresh/navigation).
`remember_me=True` → persistent Max-Age. This choice is captured once at
login (`LoginRequest.remember_me`, default `False`,
`commercial_schemas.py:27-34`) and persisted per-session on the
`RefreshToken.remember_me` column so it's re-applied identically on every
silent `/refresh` rotation (`auth_service.py:118-120`). Signup always
behaves as `remember_me=True` (no such choice at signup).

## 7. Refresh token behavior

`commercial_models.py:221-237`, table `refresh_tokens`: `id`, `user_id`
(FK), `token_hash` (SHA-256 of the raw token, unique+indexed — the raw
token is never stored), `expires_at`, `revoked_at` (nullable),
`remember_me`. Rotation (`auth_service.py:100-121`): every `/refresh` call
revokes the presented token and issues a brand-new one — a
leaked-and-reused token is detectable (the old hash is already dead) and
limited to one rotation's blast radius.

## 8. Password hashing algorithm and parameters

`security_service.py:18,23,26-34`: Argon2id via `argon2-cffi`'s
`PasswordHasher()` — **library defaults, no custom cost parameters set**.
`argon2-cffi==23.1.0` is pinned in `backend/requirements.txt`. Platform
Core's `platform-core/backend/app/security/passwords.py` uses the
identical construction (`PasswordHasher()`, same pinned version) — see
`LOADY_MIGRATION_DRY_RUN.md`'s hash-compatibility test for the actual
proof, not just this observation.

## 9. Email verification flow

Single-use, SHA-256-hashed, 48h TTL token (`generate_single_use_token`,
`security_service.py:90-98`). Table `email_verification_tokens`
(`commercial_models.py:328-336`): `user_id` FK, `token_hash` (unique),
`expires_at`, `used_at`. Endpoints: `POST /api/auth/verify-email`,
`/resend-verification` (`routes_auth.py:147-161`).

## 10. Forgot/reset password flow

Same token pattern, 1h TTL. `request_password_reset`
(`auth_service.py:133-138`) **silently no-ops for an unknown email** —
deliberate anti-enumeration. `reset_password`
(`auth_service.py:145-167`) revokes every active refresh token for that
user on success — forces re-login everywhere. Endpoints: `POST /api/auth/
forgot-password`, `/reset-password` (`routes_auth.py:133-145`).

## 11. Current session persistence / remember_me behavior

Covered fully in §6. There is no separate "session" table beyond
`RefreshToken` itself — each row *is* a session.

## 12. Admin role storage and authorization

`User.role` (`commercial_models.py:49`), plain string, `"user"`/`"admin"`
(`UserRole` enum, `commercial_enums.py:34-36`). No separate roles table.
`require_admin` (`deps.py:71-74`):
```python
def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN.value:
        raise ForbiddenError("Admin access required.")
    return user
```
Re-resolved from the DB on every request via `get_current_user` — never
cached, never trusted from a client claim. **This is Loady-scoped only** —
Loady's own "admin" has never meant anything about any other product, so
the migration maps it to `RoleAssignment(role_slug="admin",
scope="product:loady")` on Platform Core, never `scope="global"` (see
`LOADY_IDENTITY_INTEGRATION.md`).

## 13. Subscription model

`commercial_models.py:57-88`, table `subscriptions`: `id`, `user_id` (FK,
indexed), `provider` (`"paddle"`|`"gifted"`, default `"paddle"`),
`provider_customer_id`, `provider_subscription_id` (both nullable),
`plan` (`"free"`|`"pro"`|`"creator"`), `status` (`"none"`|`"active"`|
`"trialing"`|`"past_due"`|`"canceled"`|...), `current_period_start/end`,
`cancel_at_period_end`, `granted_by_admin_id` (FK, gifted-only),
`granted_reason` (gifted-only). "Active" for entitlement purposes is
`status IN ("active", "trialing", "past_due")` —
`ACTIVE_SUBSCRIPTION_STATUSES`, `account_service.py:12-16` — **"still
entitled while payment is retried"** is a real product decision this
migration must not silently discard.

## 14. Paddle customer/subscription identifiers

`Subscription.provider_customer_id` / `provider_subscription_id` — real
Paddle ids, live only in Loady's own DB. **These never migrate onto
Platform Core** — Platform Core's `Entitlement` model has no column for
them by design (see `ENTITLEMENTS.md`); the migration writes a *derived*
`Entitlement(source="paddle")` fact, and Loady keeps managing its own
Paddle relationship untouched. See `LOADY_IDENTITY_INTEGRATION.md`
§"Billing boundary is unchanged."

## 15. Plan representation

`Plan` enum: `free`/`pro`/`creator` (`commercial_enums.py`). Product-scoped
on Platform Core as `Plan(product_id="loady", slug="free"|"pro"|
"creator")`.

## 16. Entitlement/feature calculation

`app/services/plan_policy.py`'s `PLAN_POLICIES` dict is the single source
of truth for what each plan can do; `EntitlementService`/
`DownloadGateService` are the only things that ever ask it a question.
**Not modified by this mission** — see `LOADY_IDENTITY_INTEGRATION.md`
§"Scoping decision: entitlement retrieval is proven, not yet wired to the
live gate" for exactly why and what remains before it could be.

## 17. Gifted subscription implementation

Already fully built (`gift_subscription_service.py`, from an earlier
mission) — `provider="gifted"`, `granted_by_admin_id`, `granted_reason`,
paid-Paddle-takes-precedence rule, own `AdminActionLog` audit trail,
revenue-exclusion in `analytics_service.py`. The migration reuses this
exact model as the source of truth for which Loady subscriptions become
`Entitlement(source="gifted")` vs `source="paddle"`.

## 18. Download ownership relation to users

**Not in the same database as `users`.** `backend/app/database/db.py`
(raw `sqlite3`, table `history`, `db.py:21-38`) is a physically separate
SQLite file (`data/app.db`) from the commercial/SQLAlchemy DB
(`data/commercial.db`, `commercial_settings.py:48-50`). `history.user_id`
(`db.py:37`) is a plain `TEXT` column with **no `FOREIGN KEY` constraint**
(impossible across two separate SQLite files/connections anyway) —
application code (`history_repo.py`) populates it with the commercial
`User.id` string by convention, not by a DB-enforced relationship. It was
added later via an idempotent `ALTER TABLE history ADD COLUMN user_id
TEXT` (`db.py:53-56`) for backward compatibility.

**Migration implication: this is good news.** Because `history` already
joins on Loady's own `User.id` (never email, never anything from Platform
Core), adding a `global_user_id` column to Loady's `users` table changes
nothing about how history is stored, queried, or owned — `history.user_id`
keeps meaning exactly what it already means. No history row needs to be
touched by this migration at all.

## 19. Download/history foreign keys

Covered in §18 — there are no real FK constraints on `history` at all
(SQLite, separate DB file); ownership is enforced entirely by application
code always filtering `WHERE user_id = ?` with the authenticated caller's
own id (`history_repo.py`).

## 20. Usage quota/accounting relation to users

`UsagePeriod` (`commercial_models.py:91-109`) and `UsageEvent`
(`commercial_models.py:112-124`) both FK to `users.id` directly (real
SQLAlchemy FK, same DB as `users`). Unaffected by this migration — a
migrated user's existing usage/credit state is untouched; only their
*identity* row gains a `global_user_id`.

## 21. Analytics relation to users

`AnalyticsEvent` (`commercial_models.py:272-325`) has **both**
`visitor_id` (opaque, unauthenticated, nullable) and `user_id` (real FK to
`users.id`, nullable) — independent columns so anonymous page views and
authenticated events share one table without conflating the two kinds of
identity. Unaffected by this migration.

## 22. Every location where email is used as an identity/lookup key

Exhaustively greped. **Every** use of `.email` in `backend/app` falls into
one of: (a) login-time lookup/uniqueness enforcement on the `users.email`
column itself — the only place email legitimately behaves like a key;
(b) the destination address for a transactional email; (c) display-only
values in admin API responses or audit-log JSON snapshots; (d) an admin
search `ILIKE` filter. **No table anywhere stores or joins on email as a
foreign key** — `history`, `subscriptions`, `usage_periods`,
`usage_events`, `analytics_events`, `admin_action_log` all reference
`users.id` exclusively. This confirms the migration is safe to key
strictly on `global_user_id` (mapped 1:1 from Loady's own `User.id`) and
never on email for steady-state matching, per this mission's identity
principle.

## 23. Every place `user.id`/email is assumed authoritative

`user.id` (the Loady-local UUID) is the authoritative identity for every
in-database relationship (§18-21). Nothing in the codebase currently
assumes `email` is stable/authoritative for anything beyond uniqueness —
confirmed by §22's exhaustive grep. This means introducing
`global_user_id` as a *new*, additional, nullable identity column on
`users` (rather than replacing `id`) requires zero changes to `history`,
`usage_periods`, `usage_events`, `analytics_events`, or any other table —
they all keep referencing Loady's own `User.id`, unchanged, forever. This
is the basis for this mission's "do NOT replace Loady's operational
primary key" instruction being not just safe but the obviously correct
choice — there is no overwhelmingly strong reason to do otherwise, and
several strong reasons not to (every existing FK would need touching).
