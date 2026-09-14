# Outbound Product Webhooks (the Outbox)

`app/services/outbox_service.py`. Mission-brief Phases 41-43.

## The problem this solves

Without this, a product wanting to know "did this user's entitlement
just change" would have to poll `GET /api/v1/entitlements/me` (or the new
`/api/v1/service/entitlements/{user_id}`) on a timer. The outbox lets
Platform Core push a signed, timestamped event instead, without either
side trusting an inbound network request blindly (mission-brief Phase 41:
"products should not have to blindly trust inbound network requests" -
satisfied by requiring the *product* to verify Platform Core's signature
on delivery, mirroring the same HMAC shape Platform Core itself requires
from Paddle).

## Transactional outbox pattern

```python
# inside subscription_service.upsert_subscription, same session/transaction:
existing.status = status
...
session.flush()
outbox_service.enqueue(session, "entitlement.changed", product_id, {...})
```

`enqueue` just inserts an `OutboxEvent` row in the *same* DB
transaction as the state mutation it represents. This is the entire
correctness argument: if the transaction rolls back, the event never
existed; if it commits, the event is guaranteed to exist for
`deliver_pending` to eventually find, even if the process crashes
immediately after commit. No message broker, no at-least-once delivery
gap between "mutate state" and "know an event needs sending" - a
database-backed outbox is explicitly what the mission brief asked for
over introducing Kafka/RabbitMQ for a V1.

## Delivery

`deliver_pending(session, http_post, limit=100)` is a plain function, not
a background worker this mission started running anywhere (mission-brief
Phase 56: no production deployment) - a real deployment would invoke it
from a scheduler or a cron-triggered admin action. For every pending
event:

1. Find every `OAuthClient` for the event's `product_id` with a
   `webhook_url` configured (`None` product_id = every subscribed
   client). No subscribers = the event is marked `delivered` immediately
   (nothing failed; there was simply nothing to deliver to).
2. Sign the JSON body with each client's own `webhook_signing_secret`:
   `X-Platform-Signature: ts=<unix>;h1=HMAC-SHA256(secret, f"{ts}:{body}")`
   - the exact same shape Paddle uses for its own webhooks to Platform
     Core, so a developer who has already integrated one signed-webhook
     style recognizes the other.
3. One client's failure (exception or non-2xx) never blocks delivery to
   another subscribed client for the same event - each call is
   independent (verified by
   `test_one_failing_client_does_not_block_delivery_to_another`).
4. After `outbox_max_attempts` (default 5) consecutive failed delivery
   *rounds*, the event is marked `failed` and stops being retried
   automatically - an admin can inspect it via
   `GET /api/v1/admin/outbox?status=failed`.

## Configuring a client to receive webhooks

`POST /api/v1/admin/clients/{client_id}/webhook {"webhook_url": "..."}`
(super-admin only) generates a fresh signing secret and returns it
**once** - it is never retrievable again, matching the existing client-
secret precedent. Re-configuring rotates the secret.

## What is NOT built

- No background delivery worker/scheduler is deployed anywhere (by
  design - see above).
- No product-side SDK helper for verifying the signature yet
  (`outbox_service.verify_signature` is the reference implementation a
  future product integration package would wrap - see
  `V2_ARCHITECTURE.md`'s "not built" list for the SDK itself).
- No dead-letter UI beyond the plain `GET /api/v1/admin/outbox` listing.
- Event types actually emitted today: `entitlement.changed` only (from
  `subscription_service`). `user.disabled`, `user.email_changed`,
  `membership.changed` (mentioned in the mission brief as examples) are
  not emitted anywhere yet - those code paths (account status changes,
  email change, membership changes) were not touched in this mission.
