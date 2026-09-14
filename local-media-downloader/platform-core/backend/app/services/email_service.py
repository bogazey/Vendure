"""Dev/test-only email backend (mission-brief section 21: "do NOT configure
production Resend during this mission — use a development/test email
backend"). Mirrors Loady's own `email_backend="log"` fallback: every
"sent" email is just logged, never actually delivered. A real deployment
would add a Resend/SES/Postmark backend behind the same two functions.
"""
from __future__ import annotations

from app.config.logging_config import get_logger

logger = get_logger("email")


def send_verification_email(to_email: str, verify_url: str) -> None:
    logger.info("[dev email] verification email to %s: %s", to_email, verify_url)


def send_password_reset_email(to_email: str, reset_url: str) -> None:
    logger.info("[dev email] password reset email to %s: %s", to_email, reset_url)


def send_email_change_verification(to_email: str, verify_url: str) -> None:
    """Sent to the NEW address only - confirms the requester actually
    controls it before `User.email` ever changes (mission-brief Phase 19)."""
    logger.info("[dev email] email-change verification to %s: %s", to_email, verify_url)
