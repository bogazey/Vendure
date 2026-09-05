"""Per-user download storage: <DOWNLOAD_ROOT>/<user_id>/ is the ONLY
filesystem location an authenticated (commercial) user's downloads,
history files, and file-manager actions may ever touch.

This replaces the personal app's free-form, user-chosen `download_dir`
for any authenticated request: letting a signed-up web user point
downloads at an arbitrary absolute server path is an arbitrary-file-write
primitive in a hosted multi-tenant deployment (even though it was fine for
the original single-operator desktop app it was designed for - see
COMMERCIAL_ARCHITECTURE.md §4.2). `DOWNLOAD_ROOT` itself is admin/server
config (env var, see CommercialSettings), never user-editable.

Every function here is a security boundary, not a convenience helper:
- user_id is validated against a strict allow-list pattern before it ever
  touches a path, so nothing resembling `..` or a path separator can reach
  the filesystem via this route.
- A path that already exists as a symlink where a user's directory should
  be is refused outright, rather than silently followed - `mkdir(exist_ok=
  True)` would otherwise happily accept a symlink pointing anywhere.
- Every containment check resolves both sides (follows symlinks) before
  comparing, so a symlink planted *inside* an otherwise-legitimate user
  directory can't be used to escape it either.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.config.commercial_settings import get_commercial_settings
from app.utils.exceptions import InvalidPathError
from app.utils.paths import is_within, validate_directory_writable

# Matches exactly the shape of the UUIDs this app generates for User.id
# (see app/database/commercial_models.py's _uuid()). Deliberately strict -
# this is a security boundary, not a general-purpose slug validator.
_SAFE_USER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _download_root() -> Path:
    return Path(get_commercial_settings().download_root).expanduser().resolve()


def _validate_user_id(user_id: str) -> str:
    if not user_id or not _SAFE_USER_ID.match(user_id):
        raise InvalidPathError("Invalid account identifier.")
    return user_id


def user_download_dir(user_id: str, *, create: bool = True) -> Path:
    """Resolves (and by default creates) this user's own download
    directory, <DOWNLOAD_ROOT>/<user_id>/.

    Raises InvalidPathError if user_id isn't a safe path segment, if a
    symlink already occupies where this user's directory should be
    (planted-symlink attack), if the directory can't be created/written to,
    or if the resolved path would somehow fall outside DOWNLOAD_ROOT."""
    _validate_user_id(user_id)
    root = _download_root()
    target = root / user_id

    if target.is_symlink():
        raise InvalidPathError("This account's storage location is misconfigured.")

    if create:
        ok, reason = validate_directory_writable(target)
        if not ok:
            raise InvalidPathError(reason or "Could not prepare this account's download folder.")

    resolved = target.resolve()
    if not is_within(resolved, root):
        # Should be unreachable given the checks above - a single layer of
        # defense is never enough for a security boundary, so this stays.
        raise InvalidPathError("This account's storage location is invalid.")
    return resolved


def ensure_within_user_dir(path: Path, user_id: str) -> Path:
    """Raise InvalidPathError unless `path` resolves to somewhere inside
    this user's own download directory. This is the sole authorization
    check behind every open/delete/cleanup/retry filesystem action once a
    user is authenticated - no history-based fallback, no global
    download_dir fallback. Returns the resolved path for convenience."""
    user_dir = user_download_dir(user_id, create=False)
    resolved = path.resolve()
    if not is_within(resolved, user_dir):
        raise InvalidPathError("This path is outside your account's download location.")
    return resolved
