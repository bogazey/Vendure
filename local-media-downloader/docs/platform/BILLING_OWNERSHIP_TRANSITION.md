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
(`tests/test_billing_out_of_order_and_refunds.py`, 16 tests) and
exercised again end-to-end through the reconciliation engine itself
(`tests/test_loady_paddle_reconciliation.py`, 25 tests). The full
Platform Core suite (260 tests) passes with all three fixes applied.

### 5.4 (Mission 9) `adjustment.created` is not proof a refund is complete — found via a real Sandbox event

A real captured Paddle Sandbox event (a full refund of a $4.99 Loady Pro
transaction, delivered successfully to Loady's own existing webhook
endpoint) confirmed: `type: "full"`, `action: "refund"`, `reason: "other"`,
`totals.total: "499"` — and, critically, **`status: "pending_approval"`**
at the moment `adjustment.created` fired. §5.2 above (as shipped in
Mission 8) mapped `action="refund"` directly to `status="refunded"` and
applied the financial/entitlement effect immediately on `adjustment.created`,
with no reference at all to Paddle's own adjustment `status` field — i.e.
it would have revoked entitlement and marked the payment refunded before
Paddle had actually approved the refund.

Two things worth separating: **no live incident occurred** — this event
was delivered to Loady's own original webhook handler
(`paddle_service.process_webhook_event`), which has no `adjustment.*`
branch at all and simply records it as `BillingEventStatus.IGNORED`;
Platform Core's engine has never had real Sandbox credentials configured
and was never actually invoked with this event. This was a real-payload
mismatch caught in code review before Platform Core ever goes live, not a
production bug.

**Fix**: `NormalizedEvent` gained a new field, `adjustment_status`, distinct
from `status` — `status` remains the *action* classification
(`"refunded"`/`"disputed"`, from §5.2), while `adjustment_status` carries
Paddle's own approval lifecycle value verbatim (`pending_approval` is now
verified real; `approved`/`rejected` are Paddle's documented values for the
same field, not yet independently verified against a real captured event).
`_apply_adjustment_event` now returns without effect when
`adjustment_status` is `"pending_approval"` or `"rejected"` — the financial/
entitlement effect only applies once an event (in practice, a later
`adjustment.updated`) reports `adjustment_status="approved"` (or a provider
that reports no lifecycle status at all, e.g. `FakeBillingProvider`'s
synthetic test events, in which case the event is treated as final
immediately — preserving every pre-Mission-9 test's behavior unchanged).
Covered by `tests/test_paddle_provider_normalization.py` (real-payload-shaped
unit tests of the normalization itself) and three new cases in
`tests/test_billing_out_of_order_and_refunds.py`
(`test_pending_approval_refund_does_not_yet_apply`,
`test_approved_refund_after_pending_applies_effect`,
`test_rejected_adjustment_never_applies`).

**Still unverified**: the chargeback/dispute side of this same lifecycle —
this evidence only covers a refund. `PADDLE_LIVE_INPUTS_REQUIRED.md` §3
remains open for that case.

### 5.5 (Mission 10 audit) The §5.4 fix over-generalized to chargebacks — corrected

Re-auditing §5.4's own fix against "what is proven vs. assumed" found a
second, self-inflicted issue: `_apply_adjustment_event`'s new
`adjustment_status` gate was written to apply to *any* adjustment event
(`event.status in ("refunded", "disputed")`), not just refunds. That
silently extended the refund-verified `pending_approval`/`rejected`
vocabulary to chargebacks too, with **zero real evidence** that Paddle's
chargeback/dispute lifecycle uses the same `status` values, or a `status`
field with the same meaning at all — the repository contains no real
captured chargeback event of any kind (confirmed by search: no
chargeback/dispute payload file exists anywhere in this codebase). This
would have been inventing a lifecycle transition for chargebacks that
nothing proves.

The direction matters, too: for a refund, waiting for approval protects
the customer from a premature revocation (the proven bug). For a
chargeback, waiting is the risky direction for the business — the money is
already gone/disputed, and Mission 8's original design explicitly chose
"revoke immediately" as the conservative default for exactly that reason.
Letting an unverified status value silently suppress that would have
undone Mission 8's own stated protection without any evidence to justify
it.

**Fix**: the `pending_approval`/`rejected` gate now applies only when
`event.status == "refunded"`. A `disputed` (chargeback) event ignores
`adjustment_status` entirely and keeps revoking immediately on
`adjustment.created`, exactly as Mission 8 originally shipped — this is a
revert-to-conservative, not a new behavior. Covered by
`test_chargeback_with_unverified_status_still_revokes_immediately`.

**What would change this**: a real captured Paddle Sandbox chargeback/
dispute event, showing both its true `action`/event-type (still assumed to
be `action == "chargeback"` on an `adjustment.*` event — never verified)
and whatever `status` lifecycle it reports, if any. Until that exists, this
mission will not guess at it. See `PADDLE_LIVE_INPUTS_REQUIRED.md` §4.

## 6a. Decided business policy (Mission 11 — recorded, not yet all implemented/verified)

The following were previously open business decisions in
`PADDLE_LIVE_INPUTS_REQUIRED.md` §5. They are now decided by the product
owner. Nothing below authorizes a live cutover by itself — see
`PADDLE_LIVE_INPUTS_REQUIRED.md`'s blocker list for what still is required.

**Decision #5 — refund/chargeback policy:**
- An **approved** (authoritative, per §5.4's approval gate) refund revokes
  the affected Paddle-paid entitlement.
- An authoritative chargeback/dispute suspends the affected Paddle-paid
  entitlement **immediately - no grace period** (confirms Mission 8's
  original conservative default, and confirms §5.5's decision not to
  extend the refund-approval gate to chargebacks).
- The user's **account is never deleted or disabled** solely for a refund/
  chargeback. *Verified already true*: `_apply_adjustment_event` only ever
  touches `PaymentRecord`/`Entitlement` rows via `entitlement_service.revoke`
  — no code path from a refund/chargeback event reaches `User.status` or
  deletes a `User` row anywhere in `webhook_service.py`.
- Gifted/internal/lifetime/promotion/bundle/independently-sourced
  entitlements must **not** be removed merely because a Paddle entitlement
  is revoked. **Audit finding, NOT yet true today** — see §6b below. This
  is a real gap against the now-decided policy, found by code inspection
  alone (no Paddle evidence needed), and is flagged as its own blocker
  rather than silently fixed in this pass.
- Restoration after a reversed/won dispute requires **authoritative Paddle
  evidence/reconciliation** - no invented lifecycle. *Already true*: this
  codebase has no auto-restore path at all for any adjustment outcome;
  restoring access after a reversal would require a real captured Paddle
  event for that transition, which does not exist, so no such path was
  built (consistent with §5.4/§5.5's "do not guess" stance).

**Decision #6 — checkout ownership:** Loady's own Paddle checkout remains
the checkout creator for this cutover. Platform Core does **not** take over
checkout creation in this cutover; it becomes the centralized billing/
entitlement *authority* first (webhook processing, `Subscription`/
`PaymentRecord` state, entitlement resolution). Centralized checkout is
explicitly deferred to a separate future migration. *Already true*: no
code in this codebase creates a real Paddle checkout from Platform Core -
`PaddleBillingProvider.create_checkout` raises
`BillingProviderNotConfiguredError` unconditionally, and Loady's own
`/api/billing/checkout` is untouched. This decision **removes**
`PADDLE_LIVE_INPUTS_REQUIRED.md` §2's "Platform Core's own price IDs" from
this cutover's blocker list - deferred to the future checkout migration.

**Decision #7 — historical backfill:** no attempt to backfill Loady's
complete historical Paddle transaction ledger for this cutover.
Reconcile/migrate only: active subscriptions, current entitlements, the
Paddle references needed for future reconciliation
(`provider_subscription_ref`/`provider_reference`), and events from
cutover onward. Legacy history is preserved in Loady's own tables, never
fabricated into Platform Core. *Already true*: this is exactly what
`loady_paddle_reconciliation_service.py` already does - it builds one
bootstrap event per *currently paid* subscription from that row's live
snapshot; `PADDLE_LIVE_INPUTS_REQUIRED.md` §5 already documented this as
the mission's deliberate choice, not a gap. This decision simply confirms
it as final policy rather than an open question.

**Decision #8 — dual-webhook verification window:** 7 days before final
cutover (Stage 5), unless a discovered technical reason justifies
extending it. Zero unexplained entitlement/billing divergence between
Loady and Platform Core is required before proceeding, for the full
window. See `BILLING_CUTOVER_RUNBOOK.md` Stage 4, updated below.

**Decision #9 — Loady legacy billing tables:** `Subscription`/
`BillingEvent` are never deleted during cutover. Once Platform Core is
authoritative, they are retained **read-only** for rollback/audit/
reconciliation. Physical removal is explicitly out of scope for this
migration. *Already true*: nothing in this codebase writes to or deletes
Loady's own tables at any point - the reconciliation engine is read-only
on Loady's database by construction (see `BILLING_ROLLBACK_RUNBOOK.md` §2).
This decision confirms the *retention* policy going forward; enforcing
"read-only" in practice (e.g. revoking write grants on those tables once
Platform Core is authoritative) is an operational step for cutover time,
not something this codebase can enforce from here.

## 6b. Audit finding: gifted entitlements are not currently preserved across a Paddle revoke

Checking decision #5's gift-preservation clause against actual code (no
Paddle evidence involved - this is pure entitlement-resolution logic):

- The legacy `Entitlement` table (`app/services/entitlement_service.py`) is
  **one row per (user, product)**, not one row per source. When a Paddle
  subscription becomes active for a user who was previously gifted the
  same product, reconciliation's own test
  (`test_user_with_both_paid_and_gifted_entitlement`) explicitly proves
  "paid and gifted must never coexist as two separate entitlement rows" -
  the single row is overwritten to `source=paddle`. The original gift is
  only remembered in the reconciliation *report* (`gifted_preserved`), not
  in any data `entitlement_service.revoke` can consult later.
- When that Paddle subscription is later refunded/charged back,
  `_apply_adjustment_event` calls `entitlement_service.revoke(session,
  user, user, subscription.product_id, ...)`, which sets that **same
  single row** to `REVOKED` - regardless of the fact that a gift once
  existed underneath it. The user is left with no entitlement at all,
  not their pre-existing gift.
- This is a real, verifiable gap against the just-decided policy, not a
  hypothetical - it needs no Paddle evidence to confirm or fix (it never
  touches Paddle's wire format), but it does need a real design choice
  (how to detect/restore "the gift underneath" - e.g. re-querying Loady's
  own still-existing `Subscription(provider="gifted")` row for that user
  via the same reconciliation-adjacent logic, versus persisting a shadow
  record in Platform Core when paid supersedes gifted) that was not
  specified today, so it has not been implemented in this pass. Flagged as
  its own blocker in `PADDLE_LIVE_INPUTS_REQUIRED.md`.

## 6c. Entitlement-source preservation (Mission 12: §6b's gap, closed)

**Decision (product owner):** persisted shadow/source-record approach, not
runtime re-derivation from Loady's database. Implemented as a general
mechanism, not a one-off refund patch.

### Architecture chosen: extend the existing V2 source/ledger model

Audited first, per instruction, whether a source/ledger model already
existed rather than building a parallel system - it did.
`capability_service.resolve_effective_entitlements` (Mission 6/7) already
reads FIVE independent source tables every time it runs - the legacy
`Entitlement` cache, `Subscription`, `GiftedAccess`, `BundleAccess`,
`PromotionAccess` - and merges their capabilities with a documented
tie-break rank. `GiftedAccess` in particular was already built (mission-
brief Phase 13) explicitly as "a dedicated, append-by-convention history
table... separate from the single mutable `Entitlement` row" - i.e. the
exact persisted shadow/source-record model this decision calls for
already existed for admin-granted gifts. **The actual gap was narrower
than it first looked**: Loady-native gifts were never being written into
it at all - `loady_migration_service.py` (Mission 3, which predates
`GiftedAccess`) only ever wrote the single-row legacy cache. Nothing about
the resolution engine itself needed to change; only who feeds it a durable
row for a Loady gift.

A second, independent gap (found auditing what "remove/suspend only that
source" actually required): a refund/chargeback never updated
`Subscription.status`, only the legacy cache row - so even with the gift
correctly preserved, `resolve_effective_entitlements` would still have
counted the refunded Paddle subscription as active (tie-break rank 100,
beating a gift's 60), masking the very gift being preserved. Both gaps
had to close together for the mission's own worked example to actually
work end-to-end.

### Schema changes

One additive column, one Alembic migration
(`c2d4e6f8a1b3_mission_11_gifted_access_external_ref.py`, head:
`b1c3d5e7f9a0`):

```
gifted_access.external_ref  VARCHAR(200)  NULLABLE  UNIQUE
```

`NULL` for every gift granted directly in Platform Core (`gift_service.
grant_gift`, unchanged). Set to `"loady:gift:<loady_subscription_row_id>"`
only for a gift materialized from an external system - the idempotency
key that makes repeated migration/backfill runs safe (see below).
Downgrade drops the column and its unique constraint; no data migration
needed in either direction since the column is purely additive and
nothing existing ever populated it.

No new table. `Subscription.status` (already a free-text column, no DB
enum constraint) gained two new recognized values in the Python-side
`SubscriptionStatus` enum - `refunded`/`disputed` - not a schema change.

### Service changes

- **`gift_service.materialize_external_gift`** (new): idempotent on
  `external_ref` - an existing row is returned unchanged, never
  duplicated. Deliberately does NOT call `grant_gift` or its paid-
  precedence guard (`ForbiddenError` when the user already holds an
  active paid entitlement) - that guard is for a live admin action;
  backfilling a gift's own past grant must succeed regardless of what a
  Paddle subscription later did, since preserving it independently is the
  entire point. Never creates a `PaymentRecord` - identical guarantee to
  `grant_gift`.
- **`loady_migration_service.py`** (Mission 3, extended): the per-user
  loop now (a) picks whichever ACTIVE subscription wins the single legacy
  cache row by a decided provider priority (paddle > gifted, matching the
  reconciliation engine's own precedent - previously an incidental
  most-recently-updated tie-break), and (b) INDEPENDENTLY materializes
  every currently-active `gifted`-provider row into `GiftedAccess` via the
  function above, regardless of which row won (a). This is what makes
  re-running `run_migration` for an already-migrated user a safe backfill
  strategy - see below.
- **`subscription_service.suspend_for_billing_event`** (new): sets a
  `Subscription`'s status to `refunded`/`disputed` and nothing else -
  never touches a `GiftedAccess`/`BundleAccess`/`PromotionAccess` row, or
  a different `Subscription`. Respects the exact same out-of-order guard
  as `upsert_subscription` (`last_event_occurred_at`), so a stale/delayed
  event can never resurrect or incorrectly suspend a subscription a newer
  event already settled.
- **`webhook_service._apply_adjustment_event`**: now calls the function
  above (in addition to, not instead of, the existing legacy-cache
  `entitlement_service.revoke` call) whenever a refund/chargeback takes
  effect. The legacy revoke stays purely additive: Loady's own hybrid
  resolver (`platform_entitlement_service.get_authoritative_entitlement`)
  already falls back from `/entitlements/me` (legacy-only) to
  `/api/v1/capabilities/me` (`resolve_effective_entitlements`) whenever the
  legacy row reports not-entitled - so revoking it can only ever reveal a
  remaining valid source, never hide one.

### Migration/backfill behavior

Re-running `loady_migration_service.run_migration` - already an
idempotent, safe-to-repeat operation by design (Mission 3) - is the
complete backfill strategy for users migrated before this mechanism
existed: it reads Loady's gift rows fresh every time regardless of
Platform Core's current state, and `materialize_external_gift`'s
`external_ref` check means a gift already materialized in a prior run is
a no-op, never a duplicate. No separate backfill script, no direct table
edit, no dependency on Loady's database after the (re-)run completes -
once materialized, `GiftedAccess` is independently authoritative and
nothing reads Loady again for that gift.

**Known limitation, explicitly not built**: if a Loady-native gift is
later revoked or changed IN LOADY after being materialized, nothing
propagates that change into the already-materialized `GiftedAccess` row -
there is no live sync channel from Loady's gift-admin actions into
Platform Core (a separate, unaddressed integration question, adjacent to
Decision #6's "checkout stays on Loady" territory). Not fabricated or
guessed at here.

### Precedence behavior

- **Legacy single-row cache** (`entitlement_service`, `/entitlements/me`):
  provider priority paddle > gifted, most-recent tie-break within a
  provider - one winner only, by design (this row's entire purpose is a
  fast "is this user entitled at all" answer, not multi-source detail).
- **Modern resolver** (`capability_service.resolve_effective_entitlements`,
  `/capabilities/me`): every valid source contributes independently and
  simultaneously. Boolean capabilities OR together; integer capabilities
  take the max (this is what makes "the stronger plan's capability wins"
  true automatically - a Gifted Creator's higher numeric capability beats
  a coexisting Paddle Pro's lower one with no new ranking system needed,
  proven by `test_gifted_creator_stronger_than_paddle_pro_stays_effective`);
  string/enum capabilities use the existing, unchanged, pre-Mission-11
  source-KIND tie-break (`subscription` > `bundle` > `gifted` > ...) for
  which single label wins - deliberately not touched, since "which plan's
  exact string label wins" was already a documented design decision
  ("chosen so it never surprises a paying user"), not part of this gap.

### Tests

19 new tests, all passing, all against `FakeBillingProvider` (no network):

- `tests/test_loady_migration.py`: gift migration also creates a durable
  `GiftedAccess` row with correct attribution; re-running migration never
  duplicates it (2 tests).
- `tests/test_entitlement_source_preservation.py` (new file, 9 tests): the
  mission's own worked example end-to-end (Gifted Pro → Paddle Creator →
  refunded → Gifted Pro effective again, via real webhook events); Gifted
  Creator remaining effective (and winning the numeric merge) alongside a
  coexisting Paddle Pro; an expired gift never resurrecting; a revoked
  gift never resurrecting; product isolation; user isolation; a replayed
  refund webhook never duplicating a source or double-refunding; an
  out-of-order reactivation never resurrecting a refunded subscription;
  the gift re-emerging never fabricating a `PaymentRecord`.

Full suites after this work: Platform Core 279 (was 268), Loady backend
660 (untouched), Loady frontend 187 (untouched).

## 6d. Real Sandbox evidence audit (Mission 14): `subscription.updated` and refund-`approved` — zero code mismatches found

The operator ran `scripts/paddle-sandbox-evidence/collect_evidence.py`
(Mission 13) against their own real Paddle Sandbox account and captured
two genuine (`REAL_SANDBOX_EVENT`-labelled) events, field-by-field audited
against `paddle_provider.py`/`webhook_service.py`/`subscription_service.py`/
the reconciliation engine/`capability_service.py`:

**1. A real `subscription.updated`** (a scheduled cancellation on an
otherwise-active subscription):

- `data.current_billing_period.starts_at`/`.ends_at` — exactly the field
  names/nesting `_parse_paddle_datetime`/`current_period_start`/
  `current_period_end` extraction already assumed (§5.3, built from public
  docs alone, never verified until now). **Confirmed correct, no change.**
- `data.scheduled_change.action == "cancel"` — exactly what
  `cancel_at_period_end = (data.get("scheduled_change") or {}).get("action")
  == "cancel"` already checked. **Confirmed correct, no change.**
- `data.status` stayed `"active"` throughout — confirming a scheduled
  cancellation does NOT itself change `subscription.status` (access
  continues until the scheduled effective date, exactly as
  `_subscription_contributes`'s existing "canceled + period not yet over"
  logic already assumes for the OTHER case — an already-`canceled`
  status). No new gap: this event never reaches `canceled` at all until
  Paddle applies the scheduled change itself, a later event this evidence
  doesn't cover.
- `data.subscription_id` is absent on a subscription object (only
  transaction/adjustment objects reference a subscription by that key) —
  confirmed the existing fallback (`data.get("subscription_id") or
  (data.get("id") if event_type.startswith("subscription.") else None)`)
  correctly resolves to `data.id` for this event type. **No change.**

**2. A real `adjustment.updated`, `status: "approved"`** — the same
adjustment Mission 9 captured at `pending_approval`, now resolved:

- `data.status == "approved"`, `data.action == "refund"`,
  `data.transaction_id`, `data.totals.total`/`currency_code` — every field
  our normalization reads matches exactly, including the top-level
  (not `details`-nested) `totals` placement `_adjustment_amount`'s own
  docstring already called out. **Confirmed correct, no change.**
- One new field observed: a top-level `data.type` (here: `"partial"`),
  distinct from `data.items[].type` (here: `"full"` for that one item) —
  Paddle's adjustment `type` describes the adjustment as a whole relative
  to the original transaction; the item's own `type` describes just that
  item. Neither is read by `normalize_event` (partial-vs-full is instead
  derived from cumulative `refunded_amount_cents` vs. the original
  payment — already covered, and arguably more robust since it survives
  multiple partial refunds correctly). **No code change** — this is a
  fixture-fidelity note only; Mission 9's original test fixture had
  guessed `type: "full"` at the top level, which real evidence now shows
  was the wrong level for that value (harmless, since it was never read).
- **The exact question the evidence was captured to answer** — "does
  pending → approved produce the intended effect exactly once" — is now
  proven end-to-end with this real shape, not just asserted:
  `tests/test_real_evidence_adjustment_lifecycle.py` drives the REAL
  `pending_approval` (Mission 9) then `approved` (Mission 14) payloads
  through the actual `PaddleBillingProvider` + signature verification +
  `webhook_service.receive_webhook` pipeline (not `FakeBillingProvider`):
  the pending event applies nothing, the approved event applies the
  refund and revokes the entitlement exactly once, and redelivering the
  exact same approved event a second time never double-refunds.

**Conclusion: zero mismatches found.** Mission 8/9/10's implementation,
built from Paddle's public documentation, is now independently confirmed
correct by two real captured events covering the two previously-largest
unverified pieces (`current_billing_period`/`scheduled_change`, and the
refund's `pending_approval`→`approved` transition). No production code
changed as a result of this audit — only test fixtures were corrected
(the `type` field placement above) and extended with real-shape coverage.

**What this evidence does NOT cover**, left exactly as before, no
inference drawn from its absence: a chargeback/dispute of any kind. The
collector also confirmed (read-only, via Paddle's own Simulation Types
API) that **this Sandbox account's catalog exposes no chargeback- or
dispute-named simulation type at all** — not merely "untried," a real
negative finding. Combined with there being no test-card mechanism to
trigger a genuine dispute in Sandbox (Mission 13's research), a real
chargeback/dispute event is now understood to be a **Live-observation-only
limitation**, not a Sandbox-evidence gap that more Sandbox effort could
close — see `PADDLE_LIVE_INPUTS_REQUIRED.md` for the reclassified blocker
list. The existing conservative, immediate-revoke chargeback handling
(§5.5/Mission 10) is unchanged and un-touched by this finding, per
instruction: absence of Sandbox simulation support is not itself evidence
of anything about real chargeback behavior, and none was inferred.

**Sanitization statement**: every fixture added this mission
(`tests/test_paddle_provider_normalization.py`,
`tests/test_real_evidence_adjustment_lifecycle.py`) preserves the real
payloads' exact field names/nesting/shape, with every identifying value
(subscription/customer/transaction/adjustment/product/price ids, the
linked Platform Core user id, account-specific timestamps) replaced with
clearly-synthetic placeholders. The raw evidence file itself was never
committed to this repository.

Full suites after this work: Platform Core 284 (was 279), Loady backend
660 (untouched), Loady frontend 187 (untouched).

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
