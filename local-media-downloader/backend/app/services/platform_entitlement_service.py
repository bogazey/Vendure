"""Server-side, authoritative entitlement retrieval from Platform Core
(docs/platform/LOADY_IDENTITY_INTEGRATION.md).

SCOPING DECISION - read before wiring this into anything else: this
module is a proven CAPABILITY, not yet a replacement for Loady's existing
`entitlement_service`/`plan_policy`/`download_gate_service`, which
continue to gate every real download exactly as before. Swapping the live
gate to call Platform Core on every request is deliberately left as
future work (see LOADY_PRODUCTION_MIGRATION_PLAN.md's remaining
blockers) - it is a hot-path change with real availability risk (Platform
Core being briefly unreachable must never mean Loady's own paying users
can't download), and the mission this was built under explicitly
prioritizes not breaking existing behavior over completing every
architectural step in one pass. What IS proven here, with tests, is that
Loady's backend CAN correctly retrieve and validate the authoritative
entitlement server-side, never trusting anything the browser claims.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.config.commercial_settings import get_commercial_settings
from app.config.logging_config import get_logger
from app.database.commercial_models import PlatformEntitlementCache, PlatformOidcToken, User
from app.models.commercial_enums import Plan, UserStatus
from app.services import token_encryption_service

logger = get_logger("platform_entitlement")


def _server_auth_base_url(settings) -> str:
    """Same override as `platform_identity_service._server_base_url`, for
    the `/oauth/token` endpoint specifically - PLATFORM_INTERNAL_BASE_URL
    when set (e.g. a private docker-network address in staging), otherwise
    the externally reachable platform_auth_base_url unchanged."""
    return settings.platform_internal_base_url or settings.platform_auth_base_url


def _server_api_base_url(settings) -> str:
    """Same override, for `/api/v1/...` endpoints specifically."""
    return settings.platform_internal_base_url or settings.platform_api_base_url


def store_tokens(session: Session, user: User, access_token: str, refresh_token: str, expires_in: int) -> None:
    """Encrypts both tokens before they ever reach the session/DB (mission
    4, phase 4) - `record.refresh_token`/`record.access_token` hold
    ciphertext envelopes only, never the raw values, from this point
    onward."""
    encrypted_refresh = token_encryption_service.encrypt(refresh_token)
    encrypted_access = token_encryption_service.encrypt(access_token)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    record = session.get(PlatformOidcToken, user.id)
    if record is None:
        record = PlatformOidcToken(
            user_id=user.id, refresh_token=encrypted_refresh,
            access_token=encrypted_access, access_token_expires_at=expires_at,
        )
        session.add(record)
    else:
        record.refresh_token = encrypted_refresh
        record.access_token = encrypted_access
        record.access_token_expires_at = expires_at


def _refresh_access_token(record: PlatformOidcToken) -> str | None:
    settings = get_commercial_settings()
    try:
        refresh_token = token_encryption_service.decrypt(record.refresh_token)
    except token_encryption_service.TokenEncryptionError as exc:
        logger.warning("Stored Platform Core refresh token could not be decrypted: %s", type(exc).__name__)
        return None

    try:
        response = httpx.post(
            f"{_server_auth_base_url(settings)}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.platform_client_id,
                "client_secret": settings.platform_client_secret.get_secret_value(),
                "refresh_token": refresh_token,
            },
            timeout=10,
        )
    except httpx.HTTPError as exc:
        logger.warning("Platform Core token refresh failed (network): %s", exc)
        return None
    if response.status_code != 200:
        logger.warning("Platform Core token refresh rejected: %s", response.status_code)
        return None
    body = response.json()
    plaintext_access_token = body["access_token"]
    record.access_token = token_encryption_service.encrypt(plaintext_access_token)
    record.access_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.get("expires_in", 900))
    return plaintext_access_token


def get_authoritative_entitlement(session: Session, user: User) -> dict | None:
    """Returns Platform Core's authoritative view of this user's `loady`
    entitlement (`{"entitled": bool, "entitlement": {...} | None}`), or
    `None` if this account has no linked central-identity session at all
    (never yet signed in through Platform Core, or the integration isn't
    configured) - callers must treat `None` as "unknown," never as "not
    entitled."""
    settings = get_commercial_settings()
    if not settings.platform_client_id:
        return None

    record = session.get(PlatformOidcToken, user.id)
    if record is None:
        return None

    now = datetime.now(timezone.utc)
    access_token: str | None = None
    if record.access_token and record.access_token_expires_at is not None and record.access_token_expires_at > now:
        try:
            access_token = token_encryption_service.decrypt(record.access_token)
        except token_encryption_service.TokenEncryptionError as exc:
            logger.warning("Stored Platform Core access token could not be decrypted: %s", type(exc).__name__)
            access_token = None
    if access_token is None:
        access_token = _refresh_access_token(record)
        if access_token is None:
            return None

    try:
        response = httpx.get(
            f"{_server_api_base_url(settings)}/api/v1/entitlements/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        logger.warning("Platform Core entitlement lookup failed (network): %s", exc)
        return None

    if response.status_code == 401:
        # The cached access token was rejected outright (e.g. Platform
        # Core restarted with a new signing key) - one retry after a
        # forced refresh, never a silent loop.
        access_token = _refresh_access_token(record)
        if access_token is None:
            return None
        try:
            response = httpx.get(
                f"{_server_api_base_url(settings)}/api/v1/entitlements/me",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
        except httpx.HTTPError:
            return None

    if response.status_code != 200:
        logger.warning("Platform Core entitlement lookup returned %s", response.status_code)
        return None
    return response.json()


def revalidate_central_status_if_due(session: Session, user: User) -> None:
    """Bounded central-disable propagation (mission 4, phase 12 — see
    docs/platform/SESSION_REVOCATION.md). Called from `deps.get_optional_user`
    on every authenticated request for a centrally-linked user; a no-op
    for every other user (no `global_user_id`, or the integration isn't
    configured at all).

    At most once per `SESSION_REVALIDATION_INTERVAL_MINUTES`, asks
    Platform Core's `/api/v1/me/status` — the one endpoint that reports
    account status without gating on it — whether this account is still
    active, using the CURRENTLY STORED access token if it isn't expired
    yet, only refreshing when it is.

    This deliberately does NOT force a refresh up front: Platform Core's
    own `/oauth/token` refresh grant (correctly, and unrelated to this
    mission — see docs/platform/LOADY_MIGRATION_SECURITY_REVIEW.md)
    itself rejects a disabled user's refresh token with the same generic
    `invalid_grant` used for an expired/revoked one, by OAuth-spec design
    (never leaking account state through a token-endpoint error). Forcing
    a refresh first would therefore make a disabled account indistinguishable
    from an ordinary "your refresh token expired" case — exactly backwards
    for what this check exists to detect. Reusing a still-valid access
    token sidesteps that ambiguity entirely, since `/me/status` reports
    the true account status for any cryptographically valid token
    regardless of whether the account behind it is enabled.

    Only a positive, explicit `"disabled"` answer ever changes anything:
    it flips `user.status` locally, in the same request, so the caller's
    own `user.status != "active"` check immediately rejects the session.
    Any ambiguous outcome (network error, Platform Core unreachable, no
    valid access token available and the refresh grant itself failing)
    changes nothing — mirrors the same "never punish the user for an
    availability failure" principle as the entitlement hybrid model
    above. `last_status_check_at` is still updated on every attempt
    (successful or not) so an unreachable Platform Core cannot be turned
    into a request-storm of retries.

    Known bound: this reliably catches a central disable within one
    `SESSION_REVALIDATION_INTERVAL_MINUTES` window whenever a still-valid
    access token exists at check time — true for the overwhelming
    majority of cases since access tokens normally outlive the
    revalidation interval (see docs/platform/SESSION_REVOCATION.md for
    the exact SLA statement and the narrow edge case this does not cover).
    """
    if user.global_user_id is None:
        return
    settings = get_commercial_settings()
    if not settings.platform_client_id:
        return
    record = session.get(PlatformOidcToken, user.id)
    if record is None:
        return

    now = datetime.now(timezone.utc)
    interval = timedelta(minutes=settings.session_revalidation_interval_minutes)
    if record.last_status_check_at is not None and now - record.last_status_check_at < interval:
        return
    record.last_status_check_at = now
    # Committed immediately, not left for the caller's own request-scoped
    # commit: `get_optional_user` may go on to raise AuthError later in
    # THIS same request (e.g. right after this call, once it re-checks
    # `user.status`), and `deps.get_db`'s exception handler rolls the
    # session back on any such error — which would silently undo this
    # bookkeeping (and, below, the disable itself) every single time,
    # defeating both the bounded-retry guarantee and the disable
    # propagation this function exists to provide. Verified against this
    # exact failure mode during the mission 4 staging rehearsal.
    session.commit()

    access_token: str | None = None
    if record.access_token and record.access_token_expires_at is not None and record.access_token_expires_at > now:
        try:
            access_token = token_encryption_service.decrypt(record.access_token)
        except token_encryption_service.TokenEncryptionError as exc:
            logger.warning("Stored Platform Core access token could not be decrypted: %s", type(exc).__name__)
            access_token = None
    if access_token is None:
        access_token = _refresh_access_token(record)
    if access_token is None:
        return

    try:
        response = httpx.get(
            f"{_server_api_base_url(settings)}/api/v1/me/status",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        logger.warning("Platform Core status check failed (network): %s", exc)
        return

    if response.status_code != 200:
        logger.warning("Platform Core status check returned %s", response.status_code)
        return

    if response.json().get("status") == "disabled":
        user.status = UserStatus.DISABLED.value
        session.commit()  # see the comment above — must survive a later rollback in this same request
        logger.warning("Locally disabling user %s after Platform Core reported it centrally disabled.", user.id)


_LOADY_PRODUCT_ID = "loady"


def _write_cache(session: Session, user: User, live: dict) -> None:
    entitlement = live.get("entitlement") or {}
    row = session.get(PlatformEntitlementCache, (user.id, _LOADY_PRODUCT_ID))
    expires_raw = entitlement.get("expires_at")
    expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None
    if row is None:
        row = PlatformEntitlementCache(user_id=user.id, product_id=_LOADY_PRODUCT_ID)
        session.add(row)
    row.entitled = bool(live.get("entitled"))
    row.plan_slug = entitlement.get("plan_slug")
    row.source = entitlement.get("source")
    row.status = entitlement.get("status")
    row.entitlement_expires_at = expires_at
    row.checked_at = datetime.now(timezone.utc)


def get_entitlement_hybrid(session: Session, user: User) -> dict:
    """The hybrid entitlement-availability model (mission 4, phase 11 —
    see docs/platform/ENTITLEMENT_AVAILABILITY.md). This is a read-only
    capability query, never used for a security-sensitive account
    mutation, which always calls Platform Core live or fails closed
    outright.

    Returns `{"entitled": bool, "entitlement": dict | None, "source":
    "live" | "cached" | "unknown", "stale": bool, "checked_at": iso str
    | None}`:

    - `"live"`: Platform Core answered just now; the cache row is
      refreshed to match before returning.
    - `"cached"`: Platform Core was unreachable, but a last-known answer
      exists and is still within `ENTITLEMENT_CACHE_TTL_MINUTES` of when
      it was fetched — served as-is, `stale=True`, never silently treated
      as fresh.
    - `"unknown"`: Platform Core was unreachable and either no cached
      answer exists or it has aged out of the bounded TTL — always
      resolves to `entitled=False`. No indefinite grace period: an
      unreachable Platform Core can never be leveraged into permanent
      access by simply staying down.
    """
    settings = get_commercial_settings()
    live = get_authoritative_entitlement(session, user)
    if live is not None:
        _write_cache(session, user, live)
        return {**live, "source": "live", "stale": False, "checked_at": datetime.now(timezone.utc).isoformat()}

    cache = session.get(PlatformEntitlementCache, (user.id, _LOADY_PRODUCT_ID))
    if cache is None:
        return {"entitled": False, "entitlement": None, "source": "unknown", "stale": True, "checked_at": None}

    age = datetime.now(timezone.utc) - cache.checked_at
    if age > timedelta(minutes=settings.entitlement_cache_ttl_minutes):
        return {
            "entitled": False, "entitlement": None, "source": "unknown",
            "stale": True, "checked_at": cache.checked_at.isoformat(),
        }

    entitlement = None
    if cache.entitled:
        entitlement = {
            "product_id": cache.product_id, "plan_slug": cache.plan_slug,
            "source": cache.source, "status": cache.status,
            "expires_at": cache.entitlement_expires_at.isoformat() if cache.entitlement_expires_at else None,
        }
    return {
        "entitled": cache.entitled, "entitlement": entitlement, "source": "cached",
        "stale": True, "checked_at": cache.checked_at.isoformat(),
    }


def resolve_effective_plan(session: Session, user: User, local_plan: Plan) -> tuple[Plan, dict]:
    """The one call site `download_gate_service` uses to decide *which*
    plan actually gates this request (mission 5, phase 3 —
    docs/platform/ENTITLEMENT_AVAILABILITY.md's hybrid model, now wired
    into the real download gate instead of only being a proven,
    unconnected capability).

    For an account never linked to Platform Core (`global_user_id is
    None`) or when the integration isn't configured at all, this is a
    no-op: `local_plan` — Loady's own `Subscription`-derived plan — passes
    straight through unchanged, exactly as before this mission. Existing,
    non-migrated users are completely unaffected.

    For a migrated user, Platform Core becomes authoritative for *which
    plan applies*, per `get_entitlement_hybrid`:

    - `entitled=True` (source `"live"` or `"cached"`): the plan named by
      the entitlement's `plan_slug` gates the request. An unrecognized or
      missing `plan_slug` (e.g. a future plan this Loady deployment
      doesn't know about, or a malformed cache row) fails closed to
      `Plan.FREE` rather than raising — the same fail-closed choice as an
      absent entitlement, never an error that could be mistaken for "let
      it through."
    - `entitled=False` (source `"unknown"`: Platform Core unreachable AND
      either no cache row or the cache has aged out of
      `ENTITLEMENT_CACHE_TTL_MINUTES`): falls closed to `Plan.FREE`. Free
      capabilities remain available (same policy every Free user gets);
      every paid/gifted capability is denied until Platform Core is
      reachable again. This can never escalate a plan — only ever
      resolves to FREE or the exact plan Platform Core most recently
      confirmed.

    The second return value is the raw hybrid result (`source`, `stale`,
    `checked_at`, ...) purely for callers that want to log/expose it
    (e.g. an audit trail of which source gated a given download); the
    download gate itself only needs the resolved `Plan`.
    """
    settings = get_commercial_settings()
    if user.global_user_id is None or not settings.platform_client_id:
        return local_plan, {"source": "local", "stale": False, "checked_at": None}

    result = get_entitlement_hybrid(session, user)
    if not result.get("entitled"):
        return Plan.FREE, result

    plan_slug = (result.get("entitlement") or {}).get("plan_slug")
    try:
        return Plan(plan_slug), result
    except (ValueError, TypeError):
        logger.warning("Platform Core returned an unrecognized plan_slug %r for user %s; failing closed to FREE.", plan_slug, user.id)
        return Plan.FREE, result
