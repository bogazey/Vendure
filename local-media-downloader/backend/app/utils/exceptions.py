"""Clear, user-facing exception classes.

Each carries a short friendly `message` for the UI and an optional `technical`
detail that the frontend can render in a collapsible section.
"""
from __future__ import annotations


class AppError(Exception):
    status_code = 400

    def __init__(self, message: str, technical: str | None = None):
        super().__init__(message)
        self.message = message
        self.technical = technical


class UnsupportedUrlError(AppError):
    status_code = 400


class PrivateOrLoginRequiredError(AppError):
    status_code = 403


class UnavailableMediaError(AppError):
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
