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
| `PADDLE_API_KEY` (Platform Core, if checkout creation ever moves here) | Server-side Paddle Billing API key | Not yet read anywhere in Platform Core - `PaddleBillingProvider`'s network methods all raise `BillingProviderNotConfiguredError` today |
| `PADDLE_CLIENT_TOKEN` (Platform Core, if checkout creation ever moves here) | Public Paddle.js token | Not yet read anywhere in Platform Core |

Loady's own equivalents (`PADDLE_API_KEY`, `PADDLE_CLIENT_TOKEN`,
`PADDLE_WEBHOOK_SECRET`, all four price IDs) already exist and are
unaffected by this mission - they are not being replaced or duplicated,
only referenced conceptually above for context.

## 2. IDs and configuration values

- **Paddle price IDs for Platform Core's own catalog**, if/when checkout
  creation moves to Platform Core (`BILLING_CUTOVER_RUNBOOK.md` Stage 6):
  the same four IDs Loady already has configured
  (`PADDLE_PRO_MONTHLY_PRICE_ID`, `PADDLE_PRO_ANNUAL_PRICE_ID`,
  `PADDLE_CREATOR_MONTHLY_PRICE_ID`, `PADDLE_CREATOR_ANNUAL_PRICE_ID`),
  mapped into Platform Core's own `Price` table
  (`provider_price_id`/`interval`/`amount_cents`/`currency` columns
  already exist in the schema - Mission 6).
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

- **A real captured Paddle Sandbox webhook payload** for at least one
  `subscription.updated` event (with `current_billing_period` and
  `scheduled_change` populated) and one `adjustment.created` event (a
  refund and, separately, a chargeback/dispute if Sandbox can simulate
  one). This mission's `paddle_provider.py` extraction logic for these
  fields (§5.3 and §5.2 of `BILLING_OWNERSHIP_TRANSITION.md`) was built
  from Paddle's publicly documented API shape, **not verified against a
  real captured event** - this is the single most important
  Sandbox-validation step before any Live traffic touches this code path.
- **Paddle Billing dashboard access** to add Platform Core's webhook URL
  as an additional destination (Sandbox first, then Live) - see
  `BILLING_CUTOVER_RUNBOOK.md` Stage 2.
- Confirmation of Paddle's exact **adjustment event shape** for a
  chargeback specifically (this mission assumed `data.action ==
  "chargeback"` maps to a dispute; Paddle's real API may use a different
  literal value, or represent a chargeback as a separate event type
  entirely - only a real Sandbox chargeback can confirm this).

## 5. Business decisions (not technical, must be made by a human)

1. **Refund/chargeback entitlement policy** (`BILLING_OWNERSHIP_TRANSITION.md`
   §5.2's default): full refund and chargeback both revoke immediately;
   partial refund never revokes. Confirm this is the intended policy -
   in particular, whether a chargeback should have a grace period before
   revoking (since the dispute might be resolved in the merchant's favor)
   rather than this mission's conservative immediate-revoke default.
2. **Whether Loady's own Paddle checkout stays on Loady's side
   indefinitely**, or eventually moves to Platform Core
   (`BILLING_CUTOVER_RUNBOOK.md` Stage 6) - this mission takes no
   position and builds no checkout-redirect change either way.
3. **Whether historical (pre-cutover) Paddle transactions are ever
   backfilled into Platform Core's `PaymentRecord` ledger.** This mission
   deliberately does not fabricate one from a subscription's current
   snapshot alone (there is nothing to derive a historical transaction's
   amount/currency/date from without calling Paddle's own `GET
   /transactions` API) - if historical revenue reporting inside Platform
   Core is ever required, that is a new, explicit, real-API-calling
   effort, not an extension of this mission's reconciliation tool.
4. **How long the dual-webhook verification window (Stage 4) should run**
   before cutting Loady's own endpoint over - this mission suggests "a
   week" as a starting point, not a fixed requirement.
5. **Whether Loady's own `Subscription`/`BillingEvent` tables are ever
   deprioritized or removed** after a successful cutover, or kept
   indefinitely as an operational fallback - this mission recommends
   keeping them indefinitely (see `BILLING_OWNERSHIP_TRANSITION.md` §3)
   but this is ultimately a product/ops decision, not a technical
   requirement.

## 6. What this mission explicitly did NOT need from you, and why

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
