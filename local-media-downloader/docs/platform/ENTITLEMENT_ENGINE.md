# The Capability Registry and Effective Entitlement Engine

`app/services/capability_service.py`. Mission-brief Phases 5-7.

## Registry

```text
entitlement_definitions           plan_entitlements
  id                                id
  product_id -> products.id         plan_id -> plans.id
  key            "download.max_resolution"
  value_type     boolean|integer|string|enum
  description                       entitlement_definition_id -> ...
  allowed_values (enum only)        value_boolean / value_integer / value_string
                                     (exactly one populated, matching value_type)
```

A capability is declared once per product
(`capability_service.define_capability`) and given a value per plan
(`set_plan_entitlement`, which validates the value against the
declaration's `value_type` before writing - an integer capability
rejects a string, an enum capability rejects a value outside
`allowed_values`). `get_plan_capabilities(plan_id)` returns the plan's
full typed capability map. `value_integer = -1` is the reserved sentinel
for "unlimited" (`capability_service.UNLIMITED`).

This is what makes a new capability a data change, not a code change: a
product never gates a feature on `if plan_slug == "pro"` - it gates on
`capabilities["download.max_resolution"] >= requested_resolution`, and an
admin can introduce `"lifetime"` or `"enterprise"` plans later with no
Platform Core code change at all.

## Resolution

```text
resolve_effective_entitlements(session, user_id, product_id, now=None)
  -> EffectiveEntitlementResult(product_id, capabilities: dict, sources: list[EffectiveSource])
```

Gathers every currently-contributing plan grant for this user+product
from four independent sources, each producing an `EffectiveSource` entry
(never hidden, never deleted - "preserve both sources for audit/history"
from the mission brief is satisfied by simply never filtering `.sources`
down to just the winner):

1. The legacy `Entitlement` row (still-active, not-expired) - tagged
   `legacy:<source>` internally for tie-break purposes.
2. Every `Subscription` whose status is `trialing`/`active`/`past_due`,
   or `canceled` with `current_period_end` still in the future
   ("entitlement-through-period-end").
3. Every `GiftedAccess` row that is `active`, already started, and not
   past its `expires_at` (a `None` `expires_at` never expires).
4. Every `BundleAccess` that is `active` and not expired, expanded through
   `BundleProductPlan` for this specific `product_id`.

### Merge rule, per capability type

| Type | Rule | Rationale |
|---|---|---|
| boolean | OR across every contributing plan | A capability like `ads.enabled=false` (no ads) from *any* active source should win over a stricter plan elsewhere - "paid Pro + gifted Creator" should never leave the user worse off than either alone. |
| integer | max, with `-1` ("unlimited") beating any finite value | Same reasoning - the more generous source wins. |
| string / enum | the value from the single highest-ranked contributing plan | There is no natural ordering across arbitrary strings, so ties are broken by source precedence: `subscription` (100) > `bundle` (80) > `gifted`/`legacy:gifted` (60) > `legacy:paddle` (90, ranked above bundle/gifted since a live paid subscription source deserves precedence over historical rows of the same kind) > `legacy:lifetime` (85) > `legacy:promotion` (50) > `legacy:trial` (40) > `legacy:internal` (30) > `legacy:free` (10). |

Worked example straight from the mission brief: a user with a paid `Pro`
subscription (`ads.enabled=true`, `download.max_resolution=720`) and a
gifted `Creator` grant (`ads.enabled=false`, `download.max_resolution=
UNLIMITED`) resolves to `ads.enabled=True` (OR) and
`download.max_resolution=UNLIMITED` (max/unlimited-wins) - i.e.,
effectively Creator-level access - while `.sources` still lists both the
paid subscription and the gift. See
`test_capability_engine.py::test_resolution_merges_paid_and_gifted_and_preserves_both_sources`.

## What is NOT built

- No caching layer - every call re-queries all four sources. Fine for
  V1's data volumes; a real deployment integrating dozens of products
  would want the short-TTL cache mission-brief Phase 43 describes,
  invalidated by a signed `entitlement.changed` outbox event (the outbox
  event is emitted; nothing yet consumes it to invalidate a cache, since
  no cache exists to invalidate).
- No UI surfaces this to an end user or admin as a first-class page
  (Grand Admin has a read endpoint, `GET /api/v1/admin/users/{id}/
  effective-entitlements`, but no screen).
