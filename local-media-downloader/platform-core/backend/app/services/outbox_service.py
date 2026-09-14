"""Database-backed transactional outbox + signed outbound product webhooks
(mission-brief Phases 41-42).

`enqueue()` must always be called in the same session/transaction as the
state mutation it represents (never after a commit) - that is what makes
the pair atomic: if the surrounding transaction rolls back, the outbox row
never existed either, and if it commits, the event is guaranteed to exist
for `deliver_pending` to eventually pick up, even if the process crashes
immediately after commit and before any delivery attempt.

Delivery is intentionally NOT a background worker/process started by this
module (mission-brief Phase 56: no production deployment in this
mission) - `deliver_pending` is a plain, testable function a scheduler
(cron, or a call from an admin "retry" button) would invoke.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database.models import OAuthClient, OutboxEvent
from app.security import secret_encryption

HttpPost = Callable[[str, dict[str, str], bytes], int]


def enqueue(session: Session, event_type: str, product_id: str | None, payload: dict) -> OutboxEvent:
    event = OutboxEvent(event_type=event_type, product_id=product_id, payload=payload)
    session.add(event)
    session.flush()
    return event


def sign(secret: str, body: bytes, timestamp: int) -> str:
    signed_payload = f"{timestamp}:{body.decode('utf-8')}"
    return hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """The receiving side's counterpart to `sign` - a product's own
    integration package uses exactly this shape (mirrors
    `paddle_provider.verify_webhook`'s `ts=..;h1=..` format so a developer
    who has integrated one signed-webhook style already knows this one)."""
    if not header or not secret:
        return False
    parts: dict[str, str] = {}
    for chunk in header.split(";"):
        if "=" in chunk:
            key, _, value = chunk.partition("=")
            parts[key.strip()] = value.strip()
    ts, h1 = parts.get("ts"), parts.get("h1")
    if not ts or not h1:
        return False
    computed = sign(secret, body, int(ts))
    return hmac.compare_digest(computed, h1)


def _subscribed_clients(session: Session, product_id: str | None) -> list[OAuthClient]:
    query = select(OAuthClient).where(OAuthClient.is_active.is_(True), OAuthClient.webhook_url.is_not(None))
    if product_id is not None:
        query = query.where(OAuthClient.product_id == product_id)
    return list(session.execute(query).scalars().all())


def deliver_pending(session: Session, http_post: HttpPost, limit: int = 100) -> dict[str, int]:
    """`http_post(url, headers, body) -> status_code` is injected so this
    is testable without any real network call. One product's failing
    endpoint never blocks delivery to another - each client is attempted
    independently and a delivery failure to client A does not roll back or
    retry-block a successful delivery to client B for the same event."""
    settings = get_settings()
    pending = session.execute(
        select(OutboxEvent).where(OutboxEvent.status == "pending").order_by(OutboxEvent.created_at).limit(limit)
    ).scalars().all()
    delivered = failed = still_pending = 0

    for event in pending:
        clients = _subscribed_clients(session, event.product_id)
        if not clients:
            # Nothing currently subscribed to this product's webhooks -
            # not a failure; there is simply nothing to deliver to.
            event.status = "delivered"
            event.delivered_at = datetime.now(timezone.utc)
            delivered += 1
            session.flush()
            continue

        body = json.dumps({"id": event.id, "event_type": event.event_type, "payload": event.payload}).encode("utf-8")
        all_ok = True
        for client in clients:
            try:
                raw_secret = secret_encryption.decrypt(client.webhook_signing_secret_encrypted) if client.webhook_signing_secret_encrypted else ""
            except secret_encryption.SecretDecryptionError:
                # A corrupt/undecryptable secret must not crash delivery
                # to every OTHER client - treat as a per-client failure.
                all_ok = False
                event.last_error = f"{client.client_id}: secret could not be decrypted"
                continue
            ts = int(time.time())
            signature = sign(raw_secret, body, ts)
            headers = {"Content-Type": "application/json", "X-Platform-Signature": f"ts={ts};h1={signature}"}
            try:
                status_code = http_post(client.webhook_url, headers, body)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001 - one endpoint's failure must not raise out of delivery
                all_ok = False
                event.last_error = f"{client.client_id}: {type(exc).__name__}: {exc}"
                continue
            if status_code >= 300:
                all_ok = False
                event.last_error = f"{client.client_id}: HTTP {status_code}"

        event.attempts += 1
        if all_ok:
            event.status = "delivered"
            event.delivered_at = datetime.now(timezone.utc)
            delivered += 1
        elif event.attempts >= settings.outbox_max_attempts:
            event.status = "failed"
            failed += 1
        else:
            still_pending += 1
        session.flush()

    return {"delivered": delivered, "failed": failed, "pending": still_pending}
