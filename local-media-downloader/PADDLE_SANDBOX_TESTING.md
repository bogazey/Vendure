# Paddle Sandbox Testing

**Read this first:** no Paddle MCP tool or Paddle Sandbox account has been
available in either build session for this branch. This was checked twice —
once via `ToolSearch`/`SearchMcpRegistry` when this branch was first built,
and again in a follow-up session after being told a "Paddle Sandbox MCP
server is now connected and working." The second check was just as
explicit: `ListConnectors` (no keyword filter, and filtered to
paddle/billing/payments) returned an empty list, and `SearchMcpRegistry`
against paddle/billing/checkout/subscription-shaped keywords surfaced only
unrelated tools (Padlet, Chargebee, Stripe, PayPal, Pine Labs, ChartMogul —
never Paddle). **If you believe a Paddle connector is connected on your
account, it is not visible to this session** — check under claude.ai
connector settings that it's both installed AND enabled for this specific
chat/session (an installed-but-not-enabled-here connector looks identical
to "not installed" from inside a session). No Paddle Sandbox products,
prices, checkout, or webhook delivery have been exercised against a real
Paddle account in either session. Everything below is either (a) verified
locally without Paddle (signature verification, idempotency, gating logic,
and now the checkout-request code path itself — see below) or (b) a set of
exact manual steps for you to run once real Paddle Sandbox access is
available to whoever's driving, per the project's explicit instruction not
to claim success for a test that wasn't actually run.

## What's already verified (automated, no Paddle account needed)

Run these — they don't touch the network:

```bash
cd backend && source .venv/bin/activate
python -m pytest tests/test_commercial_paddle.py -v
```

Covers: HMAC signature verification (valid, wrong secret, tampered body,
missing/malformed header), idempotent replay of the same `event_id`,
unknown event types being recorded but ignored, a webhook referencing
an unknown `user_id` not crashing, `POST /api/billing/checkout` returning
a clean `502 BILLING_ERROR` (not a crash) when no price/token is
configured — the actual state of this environment right now — and
returning the right `price_id`/`client_token`/`environment` fields when
they are configured (`tests/test_commercial_api.py::TestCheckoutValidation`).

Also verified live in a real browser against a running server (no real
Paddle account involved): sign up, visit Pricing, click Upgrade → the
missing-configuration case surfaces as a clean in-page error banner with
no uncaught JS exception, rather than the checkout silently failing or
crashing the page.

## What you need to verify manually, with a real Paddle Sandbox account

### 1. Create a Paddle Sandbox account

Sign up at https://sandbox.paddle.com (a Sandbox account is entirely
separate from a live Paddle account — no real business verification
needed to start testing).

### 2. Create the four products/prices

In the Sandbox dashboard (Catalog → Products), create:

| Product | Billing period | Price |
|---|---|---|
| Pro | Monthly | $4.99 |
| Pro | Annual | $49.00 |
| Creator | Monthly | $9.99 |
| Creator | Annual | $99.00 |

Copy each price's `pri_...` ID into `backend/.env`:

```
PADDLE_PRO_MONTHLY_PRICE_ID=pri_...
PADDLE_PRO_ANNUAL_PRICE_ID=pri_...
PADDLE_CREATOR_MONTHLY_PRICE_ID=pri_...
PADDLE_CREATOR_ANNUAL_PRICE_ID=pri_...
```

### 3. Get your API key and client-side token

Developer Tools → Authentication:
- **API key** (server-side secret) → `PADDLE_API_KEY` in `backend/.env`.
  Never expose this to the frontend.
- **Client-side token** (public, safe to expose) → `PADDLE_CLIENT_TOKEN` in
  `backend/.env`. This is what `POST /api/billing/checkout` hands back to
  the frontend for Paddle.js.

### 4. Set up the webhook

Developer Tools → Notifications → add a destination pointing at:

```
https://<your-tunnel-or-public-url>/api/billing/paddle/webhook
```

Local dev has no public URL by default — use a tunnel (`ngrok http 8000`,
`cloudflared tunnel --url http://127.0.0.1:8000`, etc.) and point the
webhook at the tunnel's HTTPS URL. Subscribe to at least:
`subscription.created`, `subscription.activated`, `subscription.updated`,
`subscription.canceled`, `subscription.paused`, `subscription.resumed`,
`transaction.completed`, `transaction.payment_failed`.

Copy the webhook's signing secret into `backend/.env`:

```
PADDLE_WEBHOOK_SECRET=whsec_...
```

### 5. Frontend checkout integration

**Done** — `frontend/src/lib/paddle.ts` dynamically loads Paddle.js v2
(`https://cdn.paddle.com/paddle/v2/paddle.js`) on first use, calls
`Paddle.Environment.set()` using the `environment` field the checkout
endpoint now returns (never hardcoded — `CheckoutResponse.environment`
mirrors the server's `PADDLE_ENV`, which this build hard-restricts to
`sandbox`), initializes with the public `client_token`, and opens
`Paddle.Checkout.open({ items: [...], customData })`. `Pricing.tsx`'s
"Upgrade" button calls this instead of the old placeholder alert, and
shows a "confirming your upgrade" banner for a few seconds after Paddle's
`checkout.completed` event fires (polling `refresh()` to catch the
account update once the webhook lands — the checkout event itself is
never treated as proof of payment, per COMMERCIAL_ARCHITECTURE.md §5).

**Not exercised**: the actual `cdn.paddle.com` script load and checkout
overlay, since (a) there's no real `PADDLE_CLIENT_TOKEN`/price IDs to
initialize against, and (b) this sandbox has no general outbound network
access to third-party sites (confirmed separately — `curl` to
`youtube.com` also fails here), so even the script fetch itself couldn't
be attempted meaningfully. What *is* verified is everything up to that
point: the request to `/api/billing/checkout`, its response shape, and
the graceful, non-crashing failure path when it's unconfigured (see
above). Once real credentials are in `backend/.env`, this should work
as-is — the acceptance checklist below is what to actually click through.

### 6. End-to-end acceptance checklist

Once 1–5 are done, walk through each of these against your real Sandbox
account and confirm:

- [ ] Products/prices load correctly in the checkout overlay
- [ ] Sandbox test card (`4242 4242 4242 4242`, any future expiry/CVC)
      completes checkout
- [ ] The webhook fires and `POST /api/billing/paddle/webhook` returns 204
- [ ] `subscriptions` table now has a row for that user with the right
      `plan`, `status=active`, `current_period_start/end`
- [ ] `GET /api/account` now reflects the new plan (poll it after checkout
      — the UI intentionally doesn't trust the checkout redirect alone, see
      COMMERCIAL_ARCHITECTURE.md §5)
- [ ] The user's usage allowance updates accordingly (150 or 500 credits)
- [ ] Upgrading from Pro → Creator mid-cycle produces an `updated` webhook
      and the plan/credits change
- [ ] Cancelling from the Paddle customer portal (via `POST
      /api/billing/portal`'s returned URL) fires `subscription.canceled`,
      and the account's access reverts to Free once `current_period_end`
      passes (or immediately, depending on your Sandbox cancellation
      settings)
- [ ] Re-sending the exact same webhook event from Paddle's dashboard
      ("Replay") does **not** double-apply — `billing_events` should still
      show exactly one row for that `event_id`

### 7. Local webhook signature testing without a tunnel

You can exercise the signature-verification path without Paddle at all,
using the same HMAC scheme `paddle_service.verify_webhook_signature`
expects:

```bash
BODY='{"event_id":"evt_test1","event_type":"subscription.activated","data":{"id":"sub_test1","status":"active","custom_data":{"user_id":"<a real user id from your commercial.db>"},"items":[{"price":{"id":"<PADDLE_PRO_MONTHLY_PRICE_ID from your .env>"}}]}}'
TS=$(date +%s)
SECRET="<PADDLE_WEBHOOK_SECRET from your .env>"
SIG=$(printf '%s:%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')
curl -i -X POST http://127.0.0.1:8000/api/billing/paddle/webhook \
  -H "Content-Type: application/json" \
  -H "Paddle-Signature: ts=$TS;h1=$SIG" \
  -d "$BODY"
```

A 204 response means the signature verified and the event was processed;
check `subscriptions` in `commercial.db` for the update. This is a good way
to test the webhook handler's logic in isolation before wiring up a real
tunnel.
