# Billing Validation Package (Mission 15, Phase 35 / BILLING TEST step)

## What's safe to validate without accidental charges, separated by kind

| Kind | What it proves | Requires a real purchase? |
|---|---|---|
| Configuration verification | Loady's own Paddle env vars still present/correct post-cutover (unaffected by this migration) | No |
| Webhook endpoint verification | Platform Core's `POST /api/v1/billing/webhooks/paddle` responds (not necessarily processes) to a request — confirms the route exists and TLS/routing work | No — a malformed/unsigned test request is enough to confirm the endpoint is reachable and correctly rejects bad signatures (fail-closed), without needing a real Paddle event |
| Sandbox evidence | Already gathered (Missions 9/13/14) — refund lifecycle, subscription updates, zero mismatches | No — already done, cited not repeated |
| Live observation | Chargeback/dispute shape — cannot be produced on demand | N/A — inherently unavailable pre-Live |

## The BILLING TEST runbook step, specifically

Since this identity-only cutover does not put Platform Core's billing
stack live (Decision #6, checkout and billing authority both stay on
Loady's side until the separate `BILLING_CUTOVER_RUNBOOK.md` effort), the
runbook step is narrow:

1. Load Loady's billing/plans page for a test account — confirm it
   renders correctly post-migration (proves Loady's own Paddle
   integration, architecturally untouched, wasn't accidentally broken by
   anything in this cutover).
2. Confirm Loady's checkout flow **initializes** (reaches Paddle's
   checkout overlay) without completing a real purchase.

**No real purchase is required merely to declare billing infrastructure
healthy** — per Phase 35's explicit instruction. A completed real charge
would be a meaningful cost and risk for zero additional confidence beyond
what steps 1-2 above already provide, since this cutover does not touch
billing logic at all.

## If billing cutover is ALSO in scope for a given deployment

See `PADDLE_LIVE_CUTOVER_CHECKLIST.md` and `BILLING_CUTOVER_RUNBOOK.md` —
a fully separate, multi-stage, independently-authorized effort with its
own prerequisites, not folded into this identity cutover's BILLING TEST
step.
