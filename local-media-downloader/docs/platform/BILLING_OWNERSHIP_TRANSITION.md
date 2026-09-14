# Billing Ownership Transition: Loady's Paddle Subscriptions → Platform Core

Mission 8. Everything below describes code that was actually read, built,
and locally exercised on branch `billing-ownership-transition-v1` — no
production system, no Paddle Live account, no DNS/Cloudflare/VPS
configuration was touched. See `PADDLE_RECONCILIATION_STRATEGY.md` for the
algorithm in detail, `BILLING_CUTOVER_RUNBOOK.md`/`BILLING_ROLLBACK_RUNBOOK.md`
for the operational plans, and `PADDLE_LIVE_INPUTS_REQUIRED.md` for exactly
what a real cutover would still need from a human.

## 1. What already exists (audited, not assumed)

**Loady's side** (`backend/app/services/paddle_client.py`,
`paddle_service.py`, `app/api/routes_billing.py`,
`app/database/commercial_models.py`'s `Subscription`/`BillingEvent`):
Loady owns the entire real Paddle relationship today. Its webhook handler
(`POST /api/billing/paddle/webhook`) is the sole writer of subscription
state, keyed by `BillingEvent.provider_event_id` (a real primary key) for
webhook idempotency. `Subscription.provider` (`"paddle"` vs `"gifted"`)
is the one field every revenue query trusts; `gift_subscription_service.py`
structurally cannot reach any Paddle code (`_reject_if_paid` blocks a
gift while a real paid subscription is active). This system is mature,
tested, and **untouched by this mission**.

**Platform Core's side** — richer than a "planning only" mission would
suggest, because Missions 5-7 already built a real, generic,
multi-provider billing engine here:

- `app/services/billing/base.py` — `BillingProvider` interface,
  `NormalizedEvent`/`NormalizedSubscription` (provider-neutral shapes).
- `app/services/billing/paddle_provider.py` — real webhook signature
  verification and event normalization (ported directly from Loady's own
  `verify_webhook_signature`); every network-calling method deliberately
  raises `BillingProviderNotConfiguredError` — **no live Paddle call
  exists anywhere in this codebase**.
- `app/services/billing/fake_provider.py` — a complete in-memory provider
  used by every test and by this mission's own local reconciliation
  proof.
- `app/services/subscription_service.py` + `app/services/webhook_service.py`
  — idempotent subscription upsert (`Subscription`/`SubscriptionItem`,
  `UNIQUE(provider, provider_subscription_ref)`), idempotent webhook
  journaling (`BillingWebhookEvent`, `UNIQUE(provider, provider_event_id)`
  — a DB-level constraint, not just an application check), and a
  `PaymentRecord` ledger (the only table any revenue figure may ever sum).
- **Already wired into Loady's real download gate** (Mission 5, not this
  one): `platform_entitlement_service.resolve_effective_plan` overrides a
  migrated user's plan with Platform Core's authoritative/cached
  entitlement. This means Platform Core is *already* partially
  authoritative for a migrated Loady user's *access decision* — what was
  missing, until this mission, was any way to keep that authoritative
  view in sync with what Paddle actually says about *billing*.

Three real gaps were found in this existing engine and fixed as part of
this mission (see §5) — none of them were "not built yet" placeholders;
they were code paths that looked complete but silently did nothing under
specific, mission-required conditions.

## 2. Ownership: before cutover

**Loady owns billing.** Every Paddle customer ID, subscription ID,
webhook, and dollar of revenue is created, verified, and recorded
exclusively by Loady's own `paddle_service.py`/`routes_billing.py`. This
does not change during or immediately after this mission — nothing here
redirects Paddle's webhook URL, nothing here creates a live Paddle
checkout through Platform Core.

## 3. Ownership: after cutover

**Platform Core becomes the authoritative billing-state ledger; Loady
keeps the live Paddle relationship.** Concretely, after a real cutover
(§ see `BILLING_CUTOVER_RUNBOOK.md`):

- Paddle's webhook URL is reconfigured to point at Platform Core's
  `POST /api/v1/billing/webhooks/paddle` (the endpoint this mission's
  audited `webhook_service.py` already implements) instead of — or in
  addition to, during a transition window — Loady's own endpoint.
- Platform Core's `Subscription`/`PaymentRecord`/`Entitlement` become the
  source of truth Loady's own `platform_entitlement_service` already
  reads from for a migrated user's plan.
- Loady's own `Subscription`/`BillingEvent` tables are **not deleted or
  stopped**: they remain Loady's own operational record and its fallback
  if Platform Core is ever unreachable (the existing fail-closed hybrid
  model in `ENTITLEMENT_AVAILABILITY.md` already handles that
  availability question for entitlement *decisions*; this mission does
  not change that architecture, only feeds it real billing data).
- Loady never talks to Paddle's API directly to *create or modify* a
  subscription post-cutover in the target end-state, though this mission
  does not build that checkout-redirect change — see
  `PADDLE_LIVE_INPUTS_REQUIRED.md` for what that would need.

## 4. Explicit answers to every required design question

**Are existing Paddle customer/subscription IDs referenced or migrated?**
Referenced, never migrated as a *new* identity. Loady's
`provider_customer_id`/`provider_subscription_id` values are copied
verbatim into Platform Core's `Subscription.provider_customer_ref`/
`provider_subscription_ref` — the exact same real Paddle IDs, now known
to two systems, never regenerated or reissued. `Subscription` has a
`UNIQUE(provider, provider_subscription_ref)` constraint, so the same
Paddle subscription can never be represented by two Platform Core rows.

**How are active/trialing/past-due/paused/canceled/scheduled-cancel/
expired/failed-payment subscriptions handled?** All of Loady's normalized
`SubscriptionStatus` values map 1:1 onto Platform Core's own status
strings (both were built from the same Paddle status vocabulary — see
`paddle_service._PADDLE_STATUS_MAP` and `paddle_provider._PADDLE_STATUS_MAP`,
independently identical). `active`/`trialing`/`past_due` all grant the
legacy `Entitlement`; a scheduled cancellation
(`cancel_at_period_end=True`) leaves entitlement untouched (mission 8 fix,
§5.3, made this reach the database at all); `canceled`/`expired`/`paused`
revoke the legacy cache only once `current_period_end` has truly passed —
the modern `capability_service.resolve_effective_entitlements` correctly
grants access up to that point by reading the `Subscription` row directly
at query time, independent of the legacy cache's own timing (proven live,
see `PADDLE_RECONCILIATION_STRATEGY.md` §3). "Failed payment" is not a
distinct *subscription* state in either system — Paddle (and both
`paddle_service.py` implementations) communicate it via the subscription
itself moving to `past_due`; a separate `transaction.payment_failed`
event exists for ledger/notification purposes only and needs no separate
entitlement-affecting handler.

**How are subscriptions renewed during cutover reconciled?** The
reconciliation engine (§6) bootstraps every paid Loady subscription's
*current* snapshot as one webhook-shaped event, then replays any
additional real Paddle events from the cutover window through the exact
same idempotent pipeline. A renewal that happens between "Loady's last
known state" and "the cutover completing" is just another event in that
stream — proven live with a real `transaction.completed` event applied
after bootstrapping (`PADDLE_RECONCILIATION_STRATEGY.md` §3).

**How are delayed/out-of-order/duplicate webhooks handled?** Duplicate:
`BillingWebhookEvent`'s DB-level unique constraint makes re-delivery a
provable no-op, inherited from Mission 6. Out-of-order/delayed: **this
mission's fix** — see §5.1. Before this mission, nothing checked event
recency at all; an older event arriving after a newer one would have
silently overwritten it.

**How does Platform Core become authoritative without granting duplicate
entitlements?** `subscription_service.upsert_subscription` is a true
upsert keyed on `(provider, provider_subscription_ref)`; the legacy
`Entitlement` sync only ever creates or updates the *single* row for a
given `(user, product)` pair (`entitlement_service.grant_or_change`'s own
upsert semantics, from Mission 3). Re-running the exact same
reconciliation twice is proven idempotent (§6, and live in
`PADDLE_RECONCILIATION_STRATEGY.md` §3): `created=0` the second time,
zero duplicate rows in any of `subscriptions`, `payment_records`, or
`entitlements`.

**How does gifted access remain financially separate?** Structurally, not
just by convention: the reconciliation engine never reads or writes a
Loady subscription with `provider="gifted"` at all — it is out of scope
for a *billing* engine by construction, reported for visibility
(`gifted_preserved`) but never touched. When a user genuinely holds both
a gifted and a paid subscription (a real, tested case — Loady's own
`_reject_if_paid` should prevent this going forward, but historical data
can still contain it), the paid reconciliation always wins the single
legacy `Entitlement` row (proven: exactly one entitlement row remains,
sourced `paddle`, never two rows). No `PaymentRecord` is ever created from
a gift, and no gift ever appears in `payment_records` — verified directly
against the database in this mission's live run (0 rows, always).

**How do refunds and chargebacks affect entitlements?** **This mission's
fix** — see §5.2. A full refund (cumulative refunded amount reaches the
original payment) or a chargeback/dispute immediately revokes the
entitlement that payment funded. A **partial** refund changes only the
financial ledger (`PaymentRecord.status = "partially_refunded"`,
`refunded_amount_cents` incremented) — access is untouched, since the
customer is still paying for at least part of what they have. This
default is flagged as a business decision to confirm, not purely a
technical one — see `PADDLE_LIVE_INPUTS_REQUIRED.md`.

**How are monthly vs. annual plans represented?** Not as separate `Plan`
rows (Platform Core's `Plan` is deliberately billing-cadence-agnostic —
"pro" is one plan regardless of cadence, matching Loady's own
`Plan`/`BillingPeriod` split). The cadence is entirely a property of the
`Subscription`'s own `current_period_start`/`current_period_end` span —
a 30-day span is monthly, a ~365-day span is annual. Platform Core's
`Price.interval` field (already in the Mission 6 schema) is available to
record this explicitly per price point once real Paddle price IDs are
mapped in (see `PADDLE_LIVE_INPUTS_REQUIRED.md`); the reconciliation
engine built in this mission does not need it, since it only ever
threads period dates through, never invents a cadence.

**How are billing period and next-renewal dates preserved?** **This
mission's fix** — see §5.3. Before this mission, they weren't reachable
past subscription creation at all.

**How does rollback work if Platform Core and Loady disagree?** See
`BILLING_ROLLBACK_RUNBOOK.md`. In short: reconciliation is one-directional
and read-only on Loady's side (it never writes back to Loady's database),
so "rollback" is always "stop trusting Platform Core's billing state and
fall back to Loady's own" — a configuration change, not a data-repair
operation. A genuine disagreement between Loady's last-known snapshot and
a newer synthetic/real Paddle event is not silently resolved: the
reconciliation report's `reconciled_with_change` category shows the exact
before/after values for operator review (proven live, §6).

## 5. Three real gaps found in the existing engine, and their fixes

### 5.1 Out-of-order/delayed webhooks were never guarded against

`subscription_service.upsert_subscription` unconditionally overwrote
`status`/period fields on every call, with no check of event recency.
**Fix**: `Subscription.last_event_occurred_at` (new column, migration
`b1c3d5e7f9a0`) tracks the `occurred_at` of the most recently *applied*
event; an incoming event whose `occurred_at` is older is still recorded
(the webhook journal entry happens regardless) but has zero effect on the
subscription's live fields. Proven with a real three-event sequence
(`active` → newer `canceled` → older `past_due` arriving last) where the
older event correctly loses.

### 5.2 No refund/chargeback handling existed at all

`_TRANSACTION_EVENT_TYPES` only ever contained `"transaction.completed"`.
**Fix**: `adjustment.created`/`adjustment.updated` (Paddle Billing's real
event family for refunds and chargebacks — there is no dedicated
`transaction.refunded` event) are now normalized (`action="refund"` →
`"refunded"`, `action="chargeback"` → `"disputed"`) and applied via a new
`_apply_adjustment_event`, which correlates back to the original
`PaymentRecord` via the processor's own transaction id — which required a
second fix, below.

**A related, more subtle bug found while building this**:
`PaymentRecord.provider_reference` was being set to the *webhook
envelope's* `event_id`, never the payment processor's own transaction id.
A real refund/chargeback event naturally references the transaction id,
not the id of the webhook that first reported it — so once refunds were
implemented, they could never have found the `PaymentRecord` they were
adjusting. Fixed by adding `NormalizedEvent.provider_transaction_ref` and
preferring it as `provider_reference` when a provider supplies one.

### 5.3 Billing period / renewal date / scheduled-cancellation were structurally unreachable

`_apply_subscription_event`'s existing-subscription branch always passed
`current_period_start=existing.current_period_start`,
`current_period_end=existing.current_period_end`,
`cancel_at_period_end=existing.cancel_at_period_end` to `upsert_subscription`
— i.e. it always re-supplied whatever was already there, **regardless of
what the triggering event itself said**. A real renewal, or a customer
actually cancelling (Paddle's `scheduled_change.action="cancel"`), could
never have been recorded. Fixed by extending `NormalizedEvent` with
`current_period_start`/`current_period_end`/`cancel_at_period_end`
(`None` means "this event didn't mention it," preserving the existing
value; a real value always overwrites), extracting them from Paddle's
`current_billing_period`/`scheduled_change` fields, and threading them
through in both the create and update paths. A related fix in the same
area: the existing-subscription branch also always re-derived the OLD
plan from the subscription's current item, meaning an upgrade/downgrade
event could never change anything either — fixed by honoring a
`custom_data.plan_slug` on any follow-up event, not just the first.

All three fixes are covered by dedicated regression tests
(`tests/test_billing_out_of_order_and_refunds.py`, 12 tests) and
exercised again end-to-end through the reconciliation engine itself
(`tests/test_loady_paddle_reconciliation.py`, 25 tests). The full
Platform Core suite (260 tests) passes with all three fixes applied.

## 6. The reconciliation engine (summary — full detail in PADDLE_RECONCILIATION_STRATEGY.md)

`app/services/loady_paddle_reconciliation_service.py`: read-only on
Loady's database, one bootstrap webhook event per paid Loady subscription
(built from that row's own current snapshot), replayed through the exact
same `webhook_service.receive_webhook` pipeline a real live webhook uses
— idempotency, ordering, and refund handling are inherited, not
reimplemented. Requires Mission 3's `global_user_id` link as a
prerequisite; reports (never silently resolves) every orphaned reference,
duplicate local reference, and Loady-vs-Paddle disagreement it finds.
Dry-run and commit modes, both proven live against a real Loady-schema
SQLite database seeded through Loady's own real signup code.
