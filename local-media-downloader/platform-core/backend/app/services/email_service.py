"""Dev/test-only email backend (mission-brief section 21: "do NOT configure
production Resend during this mission — use a development/test email
backend"). Mirrors Loady's own `email_backend="log"` fallback: every
"sent" email is just logged, never actually delivered. A real deployment
would add a Resend/SES/Postmark backend behind the same two functions.

Mission 15, Phase 43 fix: unlike Loady's own `LogEmailBackend`
(`backend/app/services/email_service.py`), this module used to log the
real verification/reset/email-change URL - including its embedded,
security-sensitive token - unconditionally, regardless of environment.
Since `EMAIL_BACKEND`/`email_backend` is declared in `settings.py` but
never actually read anywhere (there is no alternate backend implemented),
there was no way to avoid this leak in a real deployment short of never
calling these functions at all. Fixed by mirroring Loady's own
`app_env`-gated pattern exactly: the real URL is only ever logged when
`app_env == "development"` (pytest's default, so existing test behavior
is unchanged); any other environment gets a redacted log line with no
token, matching Loady's `DisabledEmailBackend` message shape.
"""
from __future__ import annotations

from app.config.logging_config import get_logger
from app.config.settings import get_settings

logger = get_logger("email")


def _is_development() -> bool:
    return get_settings().app_env.strip().lower() == "development"


def send_verification_email(to_email: str, verify_url: str) -> None:
    if not _is_development():
        logger.warning("Email delivery is not configured; suppressed verification email to %s", to_email)
        return
    logger.info("[dev email] verification email to %s: %s", to_email, verify_url)


def send_password_reset_email(to_email: str, reset_url: str) -> None:
    if not _is_development():
        logger.warning("Email delivery is not configured; suppressed password reset email to %s", to_email)
        return
    logger.info("[dev email] password reset email to %s: %s", to_email, reset_url)


def send_email_change_verification(to_email: str, verify_url: str) -> None:
    """Sent to the NEW address only - confirms the requester actually
    controls it before `User.email` ever changes (mission-brief Phase 19)."""
    if not _is_development():
        logger.warning("Email delivery is not configured; suppressed email-change verification to %s", to_email)
        return
    logger.info("[dev email] email-change verification to %s: %s", to_email, verify_url)
