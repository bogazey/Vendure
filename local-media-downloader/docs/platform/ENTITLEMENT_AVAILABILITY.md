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

`get_entitlement_hybrid` is a proven, tested capability — exercised for
real in the staging rehearsal, including the failure path — but it is
**not** wired into Loady's actual download gate
(`entitlement_service`/`plan_policy`/`download_gate_service`) in this
mission. That remains Mission 3's own explicit scoping decision, restated
in `platform_entitlement_service.py`'s module docstring: swapping the
live gate to call Platform Core (even via this now-safer hybrid path) is
a hot-path behavior change for Loady's existing paying users and deserves
its own deliberate, separately-reviewed rollout — not a side effect of a
staging-infrastructure mission. What this mission adds is that when that
decision is made, the availability question it was blocked on is now
answered, implemented, and tested.
