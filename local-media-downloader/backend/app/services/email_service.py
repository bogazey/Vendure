"""Email delivery abstraction.

For local development this just logs the email (including the actual
verify/reset link) to the app log instead of requiring a real email
provider. Swap `LogEmailBackend` for a real provider (SES, Postmark,
Resend, ...) by implementing the same `EmailBackend` protocol - nothing
else in the app needs to change.
"""
from __future__ import annotations

from typing import Protocol

from app.config.logging_config import get_logger

logger = get_logger("email")


class EmailBackend(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class LogEmailBackend:
    """Writes the email to the app log rather than sending it. This is safe
    for local/dev use only - the "email" (including any reset/verify link)
    is visible to anyone who can read data/logs/app.log."""

    def send(self, to: str, subject: str, body: str) -> None:
        logger.info("EMAIL to=%s subject=%r\n%s", to, subject, body)


_backend: EmailBackend = LogEmailBackend()


def get_email_backend() -> EmailBackend:
    return _backend


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
