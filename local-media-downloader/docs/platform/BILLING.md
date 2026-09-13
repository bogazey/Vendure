# Billing boundary: Identity ≠ Entitlement ≠ Payment

Mission-brief section 11 and section 46 state this as a first-class
architecture principle, and it is enforced by table boundaries, not just
convention:

```text
Identity        who you are           users
Entitlement     what you can access   entitlements  (source-tagged)
Payment         what was actually     payment_records
                paid, when, how much
```

**An entitlement is never itself proof of payment** (mission-brief section
36). `PaymentRecord` (`app/database/models.py`) is the *only* table any
revenue figure may ever be summed from - deliberately generic
(`provider` is a free-text processor name) rather than Paddle-specific,
since a different future product might use a different processor.

No real payment processor is wired into Platform Core in V1
(mission-brief section 45: don't build public bundle checkout / payment
UI unless clearly needed) - `PaymentRecord` exists as a schema boundary,
not a live integration. This is why Grand Admin's Overview honestly reports
`revenue_available: false` with an explanatory `revenue_note`, the same
"accuracy over visual completeness" principle Loady's own analytics work
used to justify not showing MRR (`COMMERCIAL_ARCHITECTURE.md`
`docs/ANALYTICS.md`'s "what's shown and what's deliberately omitted").

## What counts as revenue, and what never does

| Source | Revenue? |
|---|---|
| `paddle` (or any future real processor, once wired) | Yes, and only when backed by a confirmed `PaymentRecord` |
| `gifted`, `internal`, `promotion` | **Never** - zero revenue, always (mission-brief section 10: "must not generate revenue") |
| `trial` | No |
| `lifetime` | Only if the lifetime grant was itself paid for - the `PaymentRecord` is what would prove that, not the `lifetime` source tag alone |
| `bundle` | Only the originating `PaymentRecord` counts; the N `Entitlement` rows a bundle purchase creates are never separately double-counted as N sales |

Every "paid" count in Grand Admin's Overview
(`paid_entitlements`) filters `Entitlement.source == "paddle"` explicitly
- the same discipline as Loady's `analytics_service.get_overview`/
`get_revenue`, which filter `Subscription.provider == "paddle"` rather
than inferring paid status from plan alone. `gifted_entitlements` is a
**separate, never-summed** counter, exactly mirroring Loady's
`gifted_subscribers` field - "never combine those into '17 paid
subscribers'" (mission-brief section 14) is enforced by these being two
different response fields, not two branches of the same number.

## A payment may fund multiple entitlements (mission-brief section 12)

`plan == payment` is never assumed. A single `PaymentRecord` for a future
"Creator Suite" bundle would be followed by several
`entitlement_service.grant_or_change` calls (one per product in the
bundle), each tagged `source=BUNDLE` - see `ENTITLEMENTS.md` §"Bundles".

## Analytics (mission-brief section 35)

Grand Admin does not centralize every raw product analytics event - Loady
already has its own first-party analytics
(`local-media-downloader/docs/ANALYTICS.md`) and keeps it; a future
"aggregate product-level summaries" view in Grand Admin would read
pre-aggregated numbers a product's own analytics service chooses to
expose, never raw per-event data. Nothing here fabricates a metric Platform
Core cannot actually compute - the `revenue_note` pattern above is the
template for how every future "we don't have real data for this yet"
case should be handled.
