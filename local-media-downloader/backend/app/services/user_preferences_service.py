"""Per-user download preferences: container_mode and cookie handling.

These used to be read straight off the personal app's global `settings`
table (one shared row for the whole process). That was fine for a
single-user local desktop app, but once downloads are gated per-account
(see download_gate_service.py) it becomes a real cross-tenant bug: any
user changing "Best Quality / Original Container" or a cookie source would
silently change what every *other* user's requests were gated and executed
against. This service is the one place that reads/writes the per-user
override; DownloadGateService and DownloadManager both go through it
instead of ever touching the global container_mode/cookie_source again.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.commercial_models import UserDownloadPreferences
from app.models.enums import ContainerMode, CookieSource
from app.models.schemas import AppSettings

# Same sensible defaults AppSettings itself declares - a user who has never
# touched these controls gets exactly the behavior they'd have gotten
# before this table existed.
DEFAULT_CONTAINER_MODE = ContainerMode.COMPATIBILITY
DEFAULT_COOKIE_SOURCE = CookieSource.NONE


class UserPreferencesService:
    def get_or_create(self, session: Session, user_id: str) -> UserDownloadPreferences:
        prefs = session.get(UserDownloadPreferences, user_id)
        if prefs is not None:
            return prefs

        prefs = UserDownloadPreferences(
            user_id=user_id,
            container_mode=DEFAULT_CONTAINER_MODE.value,
            cookie_source=DEFAULT_COOKIE_SOURCE.value,
            cookie_file_path=None,
        )
        session.add(prefs)
        try:
            session.flush()
        except IntegrityError:
            # Lost a race with a concurrent request creating the same row -
            # user_id is the primary key, so this is just "someone else won".
            session.rollback()
            prefs = session.execute(
                select(UserDownloadPreferences).where(UserDownloadPreferences.user_id == user_id)
            ).scalars().first()
            if prefs is None:
                raise
        return prefs

    def update(self, session: Session, user_id: str, patch: dict) -> UserDownloadPreferences:
        prefs = self.get_or_create(session, user_id)

        if "container_mode" in patch and patch["container_mode"] is not None:
            prefs.container_mode = ContainerMode(patch["container_mode"]).value
        if "cookie_source" in patch and patch["cookie_source"] is not None:
            prefs.cookie_source = CookieSource(patch["cookie_source"]).value
        if "cookie_file_path" in patch:
            prefs.cookie_file_path = patch["cookie_file_path"]

        effective_source = prefs.cookie_source
        if effective_source == CookieSource.FILE.value and prefs.cookie_file_path:
            cookie_path = Path(prefs.cookie_file_path).expanduser()
            if not cookie_path.is_file():
                raise ValueError(
                    "Cookie file not found at that path. Check Settings → Authentication."
                )

        session.flush()
        return prefs

    def get_effective_settings(
        self, session: Session, user_id: Optional[str], base: AppSettings
    ) -> AppSettings:
        """Convenience wrapper: `base` as-is for an anonymous caller (no
        per-user row to apply), otherwise `base` with this user's own
        container_mode/cookie_source/cookie_file_path layered on top."""
        if not user_id:
            return base
        prefs = self.get_or_create(session, user_id)
        return self.apply_to_settings(base, prefs)

    def apply_to_settings(self, base: AppSettings, prefs: UserDownloadPreferences) -> AppSettings:
        """Returns a copy of the global AppSettings with container_mode /
        cookie_source / cookie_file_path overridden by this user's own
        preferences - everything else (download_dir, concurrency, theme,
        audio format, timeouts, ...) still comes from the shared settings."""
        return base.model_copy(
            update={
                "container_mode": ContainerMode(prefs.container_mode),
                "cookie_source": CookieSource(prefs.cookie_source),
                "cookie_file_path": prefs.cookie_file_path,
            }
        )


user_preferences_service = UserPreferencesService()
