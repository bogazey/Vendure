# Central Disable / Session Revocation (Mission 4, Phase 12)

## The problem

Mission 3 found: centrally disabling a user (via Grand Admin) prevents
that user from starting any *new* central-authenticated session, but does
**not** immediately terminate a Loady session that was already open
before the disable — Loady's own `get_optional_user` only ever checked
its own local `user.status` column, which a central disable never
touched.

## Decision

Periodic, bounded central-status re-validation — not a global session
registry, not a real-time push/webhook (unjustified complexity for a V1
staging integration; nothing here rules it out as a future upgrade).

Mechanism, end to end:

1. Platform Core gained one new endpoint: `GET /api/v1/me/status`
   (`platform-core/backend/app/api/routes_v1.py`). Deliberately does
   **not** gate on `user.status` the way every other `/api/v1` route's
   `get_bearer_principal` dependency does — it returns `200` with
   `{"status": "active" | "disabled"}` for any cryptographically valid
   bearer token, regardless of whether the account behind it is enabled.
   This is the one place account status is *reported* rather than
   *enforced*, specifically so a caller can tell "this account is
   disabled" apart from "this token is invalid/expired" — both of which
   collapse into the same generic `401` everywhere else, correctly, to
   avoid leaking account state through a resource endpoint.
2. Loady gained `platform_entitlement_service.revalidate_central_status_if_due`,
   called from `deps.get_optional_user` on every authenticated request
   for a centrally-linked user (`global_user_id is not None`) — a no-op
   for every other user and for every request within
   `SESSION_REVALIDATION_INTERVAL_MINUTES` (default 5) of the last check.
3. When due, it calls `/api/v1/me/status` and, **only** on an explicit
   `"disabled"` answer, flips `user.status` locally in the same request —
   which the caller's own existing `user.status != "active"` check then
   rejects immediately.

## SLA

**Within `SESSION_REVALIDATION_INTERVAL_MINUTES` (default: 5 minutes) of
the next authenticated request the user makes, provided a still-valid
Platform Core access token exists at check time** — which is true for the
overwhelming majority of real sessions, since Platform Core's OIDC access
tokens (`OIDC_ACCESS_TOKEN_TTL_MINUTES`, default 15) normally outlive the
5-minute revalidation interval. This is **not** "within 5 minutes of the
admin clicking disable" in the abstract — it is bounded by the user's own
request activity; a user who makes no requests at all for an hour is
re-checked on their next request, whenever that is.

**Known edge case, stated plainly rather than glossed over**: if the
stored access token has already expired by the time a check becomes due,
this mechanism falls back to Platform Core's `/oauth/token` refresh
grant to get a fresh one — and that grant is *itself*, correctly and by
design, gated on `user.status` (see below). A disabled user's refresh
attempt is rejected with the same generic `invalid_grant` used for an
ordinary expired/revoked refresh token, which this code cannot safely
treat as proof of "disabled" (see "Bug 1" below) — in that specific
timing window, the disable is not confirmed by *this* check, and
propagation depends on the entitlement hybrid model's own bounded
fallback (`ENTITLEMENT_AVAILABILITY.md`) for capability checks, or a
subsequent check that happens to land while some other flow has minted a
fresh token.

**Not claimed**: instant revocation. Not claimed: a guarantee independent
of the user making a request at all (there is no background sweep in this
V1 — see "Future upgrade path" below).

## Two real bugs found and fixed during the staging rehearsal

Both were caught only by running the actual cross-container flow with a
real disable — neither was visible from unit tests alone, because both
depend on the real FastAPI dependency/exception sequencing and on
Platform Core's actual refresh-grant behavior. Documented here rather
than silently fixed, since a mission whose explicit output includes a
security-relevant SLA needs to show its work.

### Bug 1: forcing a refresh before checking status made "disabled" indistinguishable from "your refresh token expired"

The first implementation unconditionally minted a *fresh* access token
before every status check, reasoning that a freshly-minted token being
rejected could only mean the account was disabled. This is wrong:
Platform Core's `oidc_service.refresh_oidc_token` **already**, correctly,
and as reviewed in Mission 3 (`LOADY_MIGRATION_SECURITY_REVIEW.md`),
rejects a disabled user's refresh grant — with the exact same generic
`invalid_grant` used for an ordinary expired or revoked refresh token, by
OAuth-spec design, specifically to avoid leaking account state through
the token endpoint. Forcing a refresh first therefore made the one signal
this mechanism needs (a positive "disabled") indistinguishable from an
everyday, meaningless refresh failure — reproduced live: disabling a
staging user caused `_refresh_access_token` to fail with `400`, and the
disable was silently never applied.

**Fix**: use the currently-stored access token directly (if not yet
expired) for the `/me/status` call, and only fall back to a refresh when
it actually is expired — sidestepping the refresh grant's status gate
entirely for the common case. See
`test_a_still_valid_cached_access_token_is_used_directly_never_forcing_a_refresh`.

### Bug 2: the disable was rolled back by the very request that triggered it

Even after Bug 1's fix, the local disable still didn't stick. Cause:
`deps.get_optional_user` calls `revalidate_central_status_if_due`, which
mutates `user.status` in the SQLAlchemy session — and then, moments
later in the *same request*, `get_current_user` raises `AuthError` once
it re-checks that same `user.status`. `deps.get_db`'s own dependency
(`try: yield session; session.commit() / except: session.rollback()`)
sees that exception and rolls the session back — silently undoing the
disable it had just applied, on every single request, forever.

**Fix**: `revalidate_central_status_if_due` now calls `session.commit()`
itself, immediately after updating `last_status_check_at` and again
immediately after flipping `user.status` to disabled — both durable
regardless of what the rest of the request does afterward. See
`test_disable_survives_a_rollback_later_in_the_same_request`.

Both fixes were verified live in the staging rehearsal after being fixed:
disabling a real synthetic user via the real Grand Admin API, over real
HTTPS, correctly and durably disabled their real Loady staging session on
the very next request — confirmed both by the API response (`401
AUTH_REQUIRED`) and by a direct SQL query against Loady's staging
Postgres showing `status = 'disabled'` persisted.

## Future upgrade path (not built in V1)

- A background sweep (rather than piggybacking on request traffic) would
  bound the SLA independent of user activity — natural next step if a
  disabled-but-idle session turns out to matter in practice.
- A security-epoch/session-version column would let a *specific* session
  be revoked (e.g. "sign out this device") without touching account
  status at all — out of scope here; Loady's existing
  `RefreshToken`-per-session design (already revocable individually) is
  the natural place to add it later.
