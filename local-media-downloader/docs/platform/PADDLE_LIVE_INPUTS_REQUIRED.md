# Paddle Live Inputs Required (for a future, separate cutover)

This document lists exactly what will eventually be needed from a human
to move from "locally proven with synthetic/fake data" (this mission) to
a real Paddle Sandbox validation and, later, a real controlled cutover.
**Nothing on this list has been requested, entered, or stored anywhere in
this mission.** No `.env` file was created or modified with a real value,
no secret was pasted into any prompt, and no code here reads a
production credential.

## 1. Credentials (never paste these into chat — set them as environment
variables/secrets directly in whatever deployment system will run
Platform Core)

| Variable | Purpose | Where it already exists in code (unset by default) |
|---|---|---|
| `PADDLE_WEBHOOK_SECRET` (Platform Core) | Verifies `Paddle-Signature` on Platform Core's own webhook endpoint | `app/services/billing/paddle_provider.py::verify_webhook` reads `get_settings().paddle_webhook_secret` |
| ~~`PADDLE_API_KEY` (Platform Core)~~ | **Deferred (Decision #6, Mission 11)** - checkout creation stays on Loady's side for this cutover | `PaddleBillingProvider`'s network methods all raise `BillingProviderNotConfiguredError` - intentionally left that way |
| ~~`PADDLE_CLIENT_TOKEN` (Platform Core)~~ | **Deferred (Decision #6, Mission 11)** - same reason | Not read anywhere in Platform Core, by design |

Loady's own equivalents (`PADDLE_API_KEY`, `PADDLE_CLIENT_TOKEN`,
`PADDLE_WEBHOOK_SECRET`, all four price IDs) already exist and are
unaffected by this mission - they are not being replaced or duplicated,
only referenced conceptually above for context.

## 2. IDs and configuration values

- ~~Paddle price IDs for Platform Core's own catalog~~ — **not needed for
  this cutover** (Decision #6, Mission 11): checkout creation stays on
  Loady's side; Platform Core becomes the billing/entitlement authority
  without ever creating a checkout itself. Deferred to the separate future
  checkout-centralization migration, if that is ever undertaken.
- **Platform Core's own public webhook URL** once deployed (e.g.
  `https://platform.loady.cc/api/v1/billing/webhooks/paddle`) - needed to
  register it as an additional Paddle webhook destination.

## 3. Exports (for the Stage 1 dry-run against real data)

- A **read-only restore or snapshot of Loady's production `commercial.db`
  (or its Postgres equivalent)** into an isolated environment - never a
  direct connection to the live production database. This mission's
  reconciliation tool takes `--loady-database-url` as a plain argument and
  has no built-in production-safety beyond refusing any URL containing
  the literal word "production" - the operator remains responsible for
  what they point it at, exactly as documented in the CLI's own
  docstring.

## 4. Dashboard settings / verification steps

- **A real captured Paddle Sandbox `adjustment.created` refund payload -
  RECEIVED (Mission 9)**, and its **`adjustment.updated` (`status:
  "approved"`) follow-up - RECEIVED (Mission 14)**, both obtained via the
  operator-run `scripts/paddle-sandbox-evidence/collect_evidence.py`
  (Mission 13) against their own Sandbox account. Together these cover the
  full `pending_approval` → `approved` lifecycle for a real $4.99 refund -
  see `BILLING_OWNERSHIP_TRANSITION.md` §6d for the field-by-field audit.
  **Zero code mismatches found**; the exactly-once pending→approved
  behavior is now proven end-to-end against the real shape
  (`tests/test_real_evidence_adjustment_lifecycle.py`), not just asserted.
- **A real captured `subscription.updated` event (with
  `current_billing_period` and `scheduled_change` populated) - RECEIVED
  (Mission 14)**, via the same collector (a real, reversible scheduled
  cancel-then-restore against a live Sandbox subscription). Confirmed the
  exact field names/nesting `paddle_provider.py` was already extracting,
  built from public docs alone and never verified before this. **Zero
  mismatches found** - see `BILLING_OWNERSHIP_TRANSITION.md` §6d.
- **Still outstanding, and now reclassified**: a real chargeback/dispute
  event. Mission 13's collector confirmed, programmatically and
  read-only, that **this Sandbox account's own catalog exposes no
  chargeback- or dispute-named simulation type at all** - not merely
  untried. Combined with no known test-card mechanism to trigger a
  genuine dispute in Sandbox, this is no longer classified as "needs more
  Sandbox effort" - it is a **Live-observation-only limitation** (see the
  classification table below). Per explicit instruction, no chargeback
  behavior was inferred or changed from this negative finding; the
  existing conservative immediate-revoke handling (Mission 10) stands
  unchanged.
- **Paddle Billing dashboard access** to add Platform Core's webhook URL
  as an additional destination (Sandbox first, then Live) - see
  `BILLING_CUTOVER_RUNBOOK.md` Stage 2.
- Confirmation of Paddle's exact **adjustment event shape** for a
  chargeback specifically (this mission assumed `data.action ==
  "chargeback"` maps to a dispute - Paddle's public Adjustments API
  documentation independently confirms `chargeback` as a real documented
  action value, alongside `chargeback_warning`/`chargeback_reverse`, so
  the literal itself is now doc-confirmed, if not yet real-event-confirmed).
  Whether a chargeback's own `status` values match the refund's
  (`pending_approval`/`approved`/`rejected`/`reversed` - all four are
  Paddle's documented values for the adjustment `status` field generally)
  remains unconfirmed for the chargeback case specifically - see the
  Live-observation-only item above.

## 4a. Blocker classification (Mission 14)

Every remaining item, reclassified into exactly the five categories
requested, now that Sandbox evidence covers refund-approval and
subscription updates:

| Blocker | Classification |
|---|---|
| Chargeback/dispute real event shape and lifecycle | **Live-observation-only limitation** - Sandbox cannot originate a genuine card-network dispute, and this account's simulator catalog has no chargeback scenario (confirmed, not assumed). Real evidence may only ever come from observing an actual Live dispute post-cutover. |
| `PADDLE_WEBHOOK_SECRET`, Platform Core deployed in a real/monitored environment, its own public webhook URL registered | **Credentials/infrastructure blocker** - ordinary ops work, no code or evidence gap. |
| Read-only snapshot of Loady's production database for Stage 1 | **Credentials/infrastructure blocker** - access provisioning, not a code or evidence question. |
| Stage 1 dry-run → Stage 5 cutover itself (the runbook's actual execution) | **Production authorization blocker** - requires a human decision to proceed against real data/traffic, rehearsed but not something evidence or code changes can unlock. |
| Mission 3 identity migration actually run against real production users | **Production authorization blocker** - the tool is built and tested; running it against real users is an authorization + scheduling decision. |
| Anything in `paddle_provider.py`/`webhook_service.py`/`subscription_service.py`/reconciliation/entitlement resolution for refund or subscription-update handling | **None outstanding** - Mission 14's audit found zero mismatches; this category is empty for the evidence obtained so far. |

No item in the current list is a plain **code blocker** (something known
to need a code fix but not yet written) or an unaddressed **Sandbox
evidence blocker** (something more Sandbox automation could still
produce) - Missions 13/14 closed every Sandbox-reachable evidence gap that
existed, and every code gap evidence exposed (Missions 9/10/12) is already
fixed and tested.

## 5. Business decisions — DECIDED (Mission 11)

All five business decisions below are now final, recorded verbatim in
`BILLING_OWNERSHIP_TRANSITION.md` §6a. They are no longer open blockers.
Two follow-on items they created are tracked separately: §2 above
(Platform Core price IDs, deferred by Decision #6) and §6 below (a real
audit finding against Decision #5's gift-preservation clause - since
resolved).

1. **Refund/chargeback entitlement policy**: an **approved** full refund
   revokes the affected Paddle-paid entitlement. A **chargeback/dispute**
   suspends it immediately, with no grace period. The user's account is
   never deleted/disabled solely for either. Gifted/internal/lifetime/
   promotion/bundle entitlements must not be removed merely because a
   Paddle entitlement is revoked (**RESOLVED, Mission 12 — see §6**).
   Restoration after a reversed/won dispute requires real Paddle evidence,
   never an invented lifecycle.
2. **Checkout ownership**: Loady's own Paddle checkout remains the
   checkout creator for this cutover. Platform Core becomes the
   centralized billing/entitlement authority first; centralized checkout
   is a separate future migration.
3. **Historical backfill**: no attempt to backfill Loady's complete
   historical Paddle transaction ledger. Only active subscriptions,
   current entitlements, the Paddle references needed for future
   reconciliation, and post-cutover events are migrated. Legacy history
   stays in Loady's own tables.
4. **Dual-webhook verification window**: 7 days before final cutover
   (Stage 5), unless a discovered technical reason justifies extending it;
   zero unexplained entitlement/billing divergence required throughout.
5. **Loady legacy billing tables**: never deleted during cutover; retained
   read-only for rollback/audit/reconciliation once Platform Core is
   authoritative. Physical removal is explicitly out of scope for this
   migration.

## 6. Gifted-entitlement preservation gap — RESOLVED (Mission 12)

Was: "gifted entitlements are not currently preserved when a Paddle
refund/chargeback revokes the same product's entitlement" (found by
Mission 11's audit of Decision #5, see `BILLING_OWNERSHIP_TRANSITION.md`
§6b). The product owner chose the persisted shadow/source-record approach
(never re-deriving from Loady's database at runtime), implemented as a
general entitlement-source preservation mechanism - see
`BILLING_OWNERSHIP_TRANSITION.md` §6c for architecture, schema, migration/
backfill, and precedence detail. 19 new tests, all passing; full suites
(Platform Core 279, Loady backend 660, Loady frontend 187) green. No
Paddle evidence, credentials, or cutover authorization was needed for any
of it - the entire fix is Platform Core's own entitlement-resolution logic.

**One known limitation, explicitly not built** (see §6c): a Loady-native
gift's REVOKE, once materialized into `GiftedAccess`, does not propagate
backward from a later change in Loady itself - there is no live sync
channel for that. Not a blocker for cutover (Loady's own gift-admin
actions are out of scope for this migration per Decision #6's spirit), but
worth knowing if Loady's gift-admin UI is ever used again after a user's
gift has been migrated.

## 8. What this mission explicitly did NOT need from you, and why

- No Paddle API key or webhook secret, Sandbox or Live - every test and
  the live local demo used `FakeBillingProvider`'s fixed, non-secret
  local test signing key, or hand-built payloads verified by pure
  functions with no network call.
- No production database access or credentials - the live demonstration
  in `PADDLE_RECONCILIATION_STRATEGY.md` used a freshly created, throwaway
  local SQLite database seeded through Loady's own real signup code, not
  a copy of any real account data.
- No DNS, Cloudflare, VPS, or port-80 configuration - nothing in this
  mission touches network topology; the reconciliation tool and the
  webhook-processing fixes are pure application/database-layer code.
