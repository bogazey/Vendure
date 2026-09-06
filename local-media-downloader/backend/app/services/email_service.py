"""Email delivery abstraction.

For local development this just logs the email (including the actual
verify/reset link) to the app log instead of requiring a real email
provider. Production can explicitly select Resend; otherwise delivery is
disabled. Provider failures never fall back to logging message contents.
"""
from __future__ import annotations

from typing import Protocol

import httpx

from app.config.logging_config import get_logger
from app.config.commercial_settings import get_commercial_settings

logger = get_logger("email")


class EmailBackend(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class LogEmailBackend:
    """Writes the email to the app log rather than sending it. This is safe
    for local/dev use only - the "email" (including any reset/verify link)
    is visible to anyone who can read data/logs/app.log."""

    def send(self, to: str, subject: str, body: str) -> None:
        if get_commercial_settings().app_env.strip().lower() != "development":
            DisabledEmailBackend().send(to, subject, body)
            return
        logger.info("EMAIL to=%s subject=%r\n%s", to, subject, body)


class DisabledEmailBackend:
    """Production-safe placeholder that never records token-bearing content."""

    def send(self, to: str, subject: str, body: str) -> None:
        logger.warning("Email delivery is not configured; suppressed message to %s", to)


class ResendEmailBackend:
    """Best-effort delivery without exposing secrets or changing auth responses.

    Do not retry automatically: a timed-out request may already be accepted.
    Never log provider response bodies or exceptions, which may echo tokens.
    """

    def __init__(self, api_key: str, sender: str) -> None:
        self._api_key = api_key.strip()
        self._sender = sender.strip()

    def send(self, to: str, subject: str, body: str) -> None:
        if not self._api_key or not self._sender:
            logger.error("Resend delivery is not configured; set RESEND_API_KEY and EMAIL_FROM")
            return
        try:
            with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0), follow_redirects=False) as client:
                response = client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"from": self._sender, "to": [to], "subject": subject, "text": body},
                )
            if not response.is_success:
                logger.error("Resend delivery failed (HTTP %s)", response.status_code)
        except httpx.HTTPError:
            logger.error("Resend delivery failed (transport error)")


def get_email_backend() -> EmailBackend:
    settings = get_commercial_settings()
    backend = settings.email_backend.strip().lower()
    if backend == "disabled":
        return DisabledEmailBackend()
    if backend == "resend":
        return ResendEmailBackend(settings.resend_api_key.get_secret_value(), settings.email_from)
    if backend == "log" and settings.app_env.strip().lower() == "development":
        return LogEmailBackend()
    return DisabledEmailBackend()


def send_verification_email(to: str, verify_url: str) -> None:
    get_email_backend().send(
        to=to,
        subject="Verify your email",
        body=f"Confirm your email address to finish setting up your account:\n\n{verify_url}\n\n"
        "If you didn't create an account, you can ignore this message.",
    )


def send_password_reset_email(to: str, reset_url: str) -> None:
    get_email_backend().send(
        to=to,
        subject="Reset your password",
        body=f"Reset your password using this link (expires in 1 hour):\n\n{reset_url}\n\n"
        "If you didn't request this, you can ignore this message.",
    )


def send_subscription_canceled_email(to: str, plan: str, period_end: str) -> None:
    get_email_backend().send(
        to=to,
        subject="Your subscription has been canceled",
        body=f"Your {plan} subscription is canceled and will remain active until {period_end}.",
    )


def send_payment_failed_email(to: str, plan: str) -> None:
    get_email_backend().send(
        to=to,
        subject="We couldn't process your payment",
        body=f"We were unable to charge your payment method for your {plan} subscription. "
        "Please update your billing details to avoid interruption.",
    )
