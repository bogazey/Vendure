# Entitlement Gate Availability Decision (Mission 4, Phase 11)

## The question

Mission 3 deliberately did not wire Platform Core entitlement checks into
Loady's live download gate, because what should happen when Platform Core
is unavailable had not been decided. This document makes that decision.

## Options considered

**A. Fail closed.** If Platform Core is unavailable, paid/gifted features
become unavailable. Rejected as the default: Platform Core is a new,
independently-operated service; an outage there would take down paying
Loady customers' access for a feature they aren't even using yet
(migration hasn't happened). Directly contradicts the design principle
already stated in `platform_entitlement_service.py`'s own module
docstring: *"Platform Core being briefly unreachable must never mean
Loady's own paying users can't download."*

**B. Fail open using last-known entitlement, unboundedly.** Simple, but
an extended Platform Core outage (or a bug that makes it "unavailable"
indefinitely) would grant indefinite free access. Also rejected: no
bounded TTL means a stale grant, a bug in a bit of the DB, or an actual
security incident.

**C. Hybrid: security-sensitive/account mutations fail closed; existing
product capabilities use a short-lived, bounded last-known-entitlement
cache.** **Selected.**

## Selected model

Two different classes of operation get two different treatments:

| Operation class | Behavior when Platform Core is unavailable |
|---|---|
| Read-only capability check ("does this user currently have Creator?") | Serve the last-known answer, but only if it was fetched within `ENTITLEMENT_CACHE_TTL_MINUTES` (default 15). Older than that → treated as **not entitled**, never as "still entitled." |
| Security-sensitive mutation (grant, revoke, role change, central disable) | Always calls Platform Core live. If unreachable, the mutation simply fails (via Grand Admin, which already requires a live central session) — never inferred from a cache. |

Implementation: `PlatformEntitlementCache` (one row per
`user_id`+`product_id`) and
`platform_entitlement_service.get_entitlement_hybrid()`
(`backend/app/services/platform_entitlement_service.py`).

```
get_entitlement_hybrid(session, user):
    live = get_authoritative_entitlement(session, user)   # always tries live first
    if live is not None:
        write_cache(live)                                  # cache always refreshed on success
        return {..., "source": "live", "stale": False}

    cache = read_cache(user)
    if cache is None or now - cache.checked_at > TTL:
        return {"entitled": False, "entitlement": None, "source": "unknown", "stale": True}

    return {**cache, "source": "cached", "stale": True}
```

### Requirements checklist (from the mission brief)

- **Server-side only** — the cache lives in Loady's own Postgres table,
  never in a cookie or any browser-readable location.
- **Tied to `global_user_id`** — keyed by `user.id`, which is only ever
  populated once a user has a `global_user_id` and a linked
  `PlatformOidcToken` row (dormant otherwise).
- **Product-specific** — `product_id` is a real column (currently always
  `"loady"` for this integration, but the schema doesn't assume a single
  product).
- **Plan/source/status included** — `plan_slug`, `source`, `status` are
  all cached verbatim from Platform Core's own response, never
  re-derived or guessed.
- **Bounded TTL, no indefinite stale access** — `ENTITLEMENT_CACHE_TTL_MINUTES`
  (default 15); verified by test
  (`test_cache_older_than_ttl_is_never_served_falls_back_to_unentitled`)
  and live in the staging rehearsal (Platform Core's containers stopped;
  the cached gifted entitlement was correctly served as `stale=True`
  within the window — an older cache row is proven, by the same test, to
  fall back to `entitled=False` instead).
- **No browser authority** — nothing here is ever read from a
  client-supplied header, cookie, or claim; every value originates from a
  signature-verified Platform Core response.
- **Central responses validated** — `get_authoritative_entitlement` only
  ever accepts a `200` response to a request carrying a bearer access
  token whose signature, issuer, audience, and expiry were already
  checked by Platform Core (`introspect_oidc_access_token`).
- **Revocation behavior** — see below.
- **Cache invalidated/refreshed appropriately** — every successful live
  call overwrites the cache unconditionally (proven live: revoking a
  gifted entitlement centrally, then calling with Platform Core reachable
  again, correctly wrote `entitled: false` back into the cache
  immediately — see
  `test_revocation_is_reflected_immediately_on_the_next_live_call`).
- **Gifted/paid source preserved** — `source` (`"gifted"`, `"paddle"`,
  etc.) is cached and returned unchanged; proven live during the staging
  rehearsal (a gifted "creator" entitlement round-tripped through the
  stale-cache path with `source: "gifted"` intact).

### Revocation behavior, explicitly

If an admin revokes an entitlement while Platform Core is reachable, the
very next capability check (live) reflects it immediately — there is no
propagation delay in the common case. The **only** window where a revoked
entitlement can still appear to be granted is: Platform Core became
unreachable *before* the revocation could be checked live, and the cache
row predates the revocation — in that case, the stale cache is served for
up to `ENTITLEMENT_CACHE_TTL_MINUTES` from when it was last fetched, not
from when the revocation happened. This is the same bounded-staleness
trade-off inherent to any cache-based availability strategy; a shorter
TTL narrows it directly at the cost of more calls to Platform Core.

## What is and isn't wired into Loady's live gate

**Update — Mission 5, phase 3: now wired, for migrated accounts only.**
`platform_entitlement_service.resolve_effective_plan(session, user,
local_plan)` is the one new call site, invoked from
`routes_downloads.py::_gate_and_create` immediately after Loady's own
`account_service.get_current_plan` resolves the local plan, and before
`download_gate_service.authorize_and_reserve` runs. It is intentionally a
thin wrapper around `get_entitlement_hybrid` — no new availability
behavior was invented for this wiring, only a decision about which `Plan`
value the existing hybrid result maps onto:

```
resolve_effective_plan(session, user, local_plan):
    if user.global_user_id is None or not settings.platform_client_id:
        return local_plan                      # non-migrated account: unchanged, Platform Core never consulted

    hybrid = get_entitlement_hybrid(session, user)
    if not hybrid.entitled:
        return Plan.FREE                        # not entitled, or unreachable + no/expired cache: fail closed
    return Plan(hybrid.entitlement.plan_slug)   # unrecognized/malformed plan_slug also fails closed to Plan.FREE
```

**Exact TTL**: `ENTITLEMENT_CACHE_TTL_MINUTES`, default **15 minutes**
(`backend/app/config/commercial_settings.py`) — unchanged from Mission 4;
phase 3 did not touch the TTL, only added a consumer of it.

**Scope of the change**: this affects *only* accounts with a non-null
`global_user_id` (i.e. accounts that completed the Platform Core identity
migration) on an environment where `PLATFORM_CLIENT_ID` is configured.
Every other account's download gate is byte-for-byte unchanged — verified
by the full existing `test_commercial_download_gate.py` /
`test_commercial_entitlement.py` suites still passing unmodified. Loady's
plan *capabilities themselves* (`plan_policy.PLAN_POLICIES`) were not
touched at all; only the source of truth for *which plan applies* changes,
and only for migrated users.

**Tests**: `backend/tests/test_platform_entitlement_gate.py` — Free, Pro
(Paddle), Creator (Paddle), Gifted Pro, Gifted Creator, expired gift,
revoked gift, Platform Core offline with a valid cache, Platform Core
offline with an expired cache, and an unrecognized/malformed `plan_slug`
(the local defense complementing Platform Core's own server-side
product-scoping — see `platform-core/backend/tests/test_entitlements.py
::test_wrong_product_denied`, which proves a client can never even receive
another product's entitlement in the first place). Disabled users are not
re-tested here: `deps.get_optional_user`'s existing central-disable
revalidation (Mission 4, phase 12) means a disabled user never reaches the
download gate at all.

**Known follow-up gap (not addressed by this wiring, tracked in
`PRODUCTION_READINESS_CHECKLIST.md`)**: Loady's account-page plan display
still reads only the local `Subscription` row. A migrated user granted a
plan *exclusively* through Platform Core (e.g. a post-migration Grand
Admin gift, with no corresponding local `Subscription` row) will now
correctly get gated at that plan by the download endpoint, while the
account page still displays "Free." Fixing this requires touching
`routes_account.py` and the Loady frontend, which is out of scope for
"wire the download gate" — tracked as a LOW/MEDIUM follow-up, not a
blocker, since it is a display inconsistency, not an authorization bug
(the gate itself is correct in both directions).
