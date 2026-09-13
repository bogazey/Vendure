"""Structured application errors — same `AppError` base pattern Loady uses
(a stable `code` the caller can branch on, a plain-English `message`, and
an HTTP `status_code`), wired to a single exception handler in `main.py`.
"""
from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "APP_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AuthError(AppError):
    status_code = 401
    code = "AUTH_REQUIRED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class EmailAlreadyRegisteredError(AppError):
    status_code = 409
    code = "EMAIL_ALREADY_REGISTERED"


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "INVALID_CREDENTIALS"


class AccountDisabledError(AppError):
    status_code = 403
    code = "ACCOUNT_DISABLED"


class InvalidTokenError(AppError):
    status_code = 400
    code = "INVALID_TOKEN"


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"


class InvalidClientError(AppError):
    status_code = 400
    code = "INVALID_CLIENT"


class InvalidRedirectUriError(AppError):
    status_code = 400
    code = "INVALID_REDIRECT_URI"


class InvalidGrantError(AppError):
    status_code = 400
    code = "INVALID_GRANT"


class InvalidPlanError(AppError):
    status_code = 422
    code = "INVALID_PLAN"


class InvalidWebhookSignatureError(AppError):
    status_code = 401
    code = "INVALID_WEBHOOK_SIGNATURE"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class InsufficientScopeError(AppError):
    status_code = 403
    code = "INSUFFICIENT_SCOPE"


class ProviderNotConfiguredError(AppError):
    status_code = 501
    code = "PROVIDER_NOT_CONFIGURED"
