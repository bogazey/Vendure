"""Clear, user-facing exception classes.

Each carries a short friendly `message` for the UI and an optional `technical`
detail that the frontend can render in a collapsible section.
"""
from __future__ import annotations


class AppError(Exception):
    status_code = 400
    # Stable, machine-readable code the frontend can branch on (e.g. to show
    # an "Upgrade to Pro" button instead of a generic error banner). None for
    # errors that are purely human-readable messages with no special UI.
    code: str | None = None

    def __init__(self, message: str, technical: str | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.technical = technical
        if code is not None:
            self.code = code


class UnsupportedUrlError(AppError):
    status_code = 400


class PrivateOrLoginRequiredError(AppError):
    status_code = 403


class UnavailableMediaError(AppError):
    status_code = 404


class NoDownloadableMediaError(AppError):
    """The post/page was reached and is accessible, but genuinely contains
    no media Loady can download (as opposed to UnavailableMediaError, which
    means the content itself is gone/private)."""

    status_code = 404


class GeoRestrictedError(AppError):
    status_code = 451


class AgeRestrictedError(AppError):
    status_code = 403


class NetworkError(AppError):
    status_code = 502


class FfmpegMissingError(AppError):
    status_code = 503


class FfmpegProcessingError(AppError):
    """FFmpeg ran but failed (or was cancelled) while merging/converting a
    file - distinct from FfmpegMissingError (binary not found at all)."""

    status_code = 502


class FormatUnavailableError(AppError):
    status_code = 400


class DiskFullError(AppError):
    status_code = 507


class PermissionDeniedError(AppError):
    status_code = 403


class ExtractorFailureError(AppError):
    status_code = 502


class InvalidPathError(AppError):
    status_code = 400


class JobNotFoundError(AppError):
    status_code = 404


# --- Auth ---------------------------------------------------------------

class AuthError(AppError):
    status_code = 401
    code = "AUTH_REQUIRED"


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "INVALID_CREDENTIALS"


class EmailAlreadyRegisteredError(AppError):
    status_code = 409
    code = "EMAIL_ALREADY_REGISTERED"


class AccountDisabledError(AppError):
    status_code = 403
    code = "ACCOUNT_DISABLED"


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class InvalidTokenError(AppError):
    status_code = 400
    code = "INVALID_TOKEN"


# --- Plans / entitlements / usage ---------------------------------------

class PlanLimitReachedError(AppError):
    status_code = 402
    code = "PLAN_LIMIT_REACHED"


class DailyLimitReachedError(AppError):
    status_code = 402
    code = "DAILY_LIMIT_REACHED"


class FeatureNotIncludedError(AppError):
    status_code = 402
    code = "FEATURE_NOT_INCLUDED"


class UpgradeRequiredError(AppError):
    status_code = 402
    code = "UPGRADE_REQUIRED"


class InsufficientCreditsError(AppError):
    status_code = 402
    code = "INSUFFICIENT_CREDITS"


# --- Billing --------------------------------------------------------------

class BillingError(AppError):
    status_code = 502
    code = "BILLING_ERROR"


class InvalidWebhookSignatureError(AppError):
    status_code = 400
    code = "INVALID_WEBHOOK_SIGNATURE"
