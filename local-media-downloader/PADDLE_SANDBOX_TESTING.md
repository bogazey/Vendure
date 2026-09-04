# Paddle Sandbox Testing

**Read this first:** no Paddle MCP tool or Paddle Sandbox account was
available in the environment this branch was built in. This was confirmed
by searching for a Paddle connector (`ToolSearch`, `SearchMcpRegistry`) —
none was found, despite the task description assuming one was connected. No
Paddle Sandbox products, prices, checkout, or webhook delivery were
actually exercised against a real Paddle account. Everything below is
either (a) verified locally without Paddle (signature verification,
idempotency, gating logic — all covered by
`backend/tests/test_commercial_paddle.py`) or (b) a set of exact manual
steps for you to run once you have Paddle Sandbox access, per the
project's explicit instruction not to claim success for a test that wasn't
actually run.

## What's already verified (automated, no Paddle account needed)

Run these — they don't touch the network:

```bash
cd backend && source .venv/bin/activate
python -m pytest tests/test_commercial_paddle.py -v
```

Covers: HMAC signature verification (valid, wrong secret, tampered body,
missing/malformed header), idempotent replay of the same `event_id`,
unknown event types being recorded but ignored, and a webhook referencing
an unknown `user_id` not crashing.

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

### 5. Frontend checkout integration (not wired up yet)

The Pricing page (`frontend/src/pages/Pricing.tsx`) currently calls `POST
/api/billing/checkout`, gets back `{price_id, client_token, ...}`, and
shows an alert with those values rather than actually opening Paddle's
checkout overlay — Paddle.js itself was never loaded or exercised, since
doing so meaningfully requires a live Sandbox client token. To finish this:

1. Add the Paddle.js script tag (`https://cdn.paddle.com/paddle/v2/paddle.js`).
2. `Paddle.Initialize({ token: clientToken })` using the `client_token` the
   checkout endpoint returns.
3. `Paddle.Checkout.open({ items: [{ priceId: checkout.price_id }],
   customData: checkout.custom_data })`.
4. Replace the `window.alert(...)` placeholder in `Pricing.tsx`'s
   `handleSelect` with the above.

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
