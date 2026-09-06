"""Per-guest download storage: <DOWNLOAD_ROOT>/_guests/<guest_id>/ is the
ONLY filesystem location an anonymous guest's downloads may ever touch.

Mirrors user_storage_service.py's security boundary exactly (symlink-plant
defense, resolved-path containment check) but nests guests under their own
`_guests/` subtree, distinctly separate from `<DOWNLOAD_ROOT>/<user_id>/` -
a guest can never be confused with, or escape into, a real account's
directory, and vice versa.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from app.config.commercial_settings import get_commercial_settings
from app.utils.exceptions import InvalidPathError
from app.utils.paths import is_within, validate_directory_writable

_GUESTS_SUBDIR = "_guests"

# secrets.token_urlsafe(32) produces ~43 URL-safe base64 characters - this
# is deliberately narrower than user_storage_service's pattern (a real
# minimum length, not just "looks like a slug") since guest ids are the
# only thing standing between one guest's files and another's.
_SAFE_GUEST_ID = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def _guests_root() -> Path:
    return Path(get_commercial_settings().download_root).expanduser().resolve() / _GUESTS_SUBDIR


def _validate_guest_id(guest_id: str) -> str:
    if not guest_id or not _SAFE_GUEST_ID.match(guest_id):
        raise InvalidPathError("Invalid guest identifier.")
    return guest_id


def guest_download_dir(guest_id: str, *, create: bool = True) -> Path:
    """Resolves (and by default creates) this guest's own download
    directory, <DOWNLOAD_ROOT>/_guests/<guest_id>/."""
    _validate_guest_id(guest_id)
    root = _guests_root()
    target = root / guest_id

    if target.is_symlink():
        raise InvalidPathError("This guest session's storage location is misconfigured.")

    if create:
        ok, reason = validate_directory_writable(target)
        if not ok:
            raise InvalidPathError(reason or "Could not prepare guest download folder.")

    resolved = target.resolve()
    if not is_within(resolved, root):
        raise InvalidPathError("This guest session's storage location is invalid.")
    return resolved


def ensure_within_guest_dir(path: Path, guest_id: str) -> Path:
    """Raise InvalidPathError unless `path` resolves to somewhere inside
    this guest's own download directory - the sole authorization check
    behind guest file cleanup, exactly like ensure_within_user_dir for
    authenticated users."""
    guest_dir = guest_download_dir(guest_id, create=False)
    resolved = path.resolve()
    if not is_within(resolved, guest_dir):
        raise InvalidPathError("This path is outside this guest session's download location.")
    return resolved


def remove_guest_dir(guest_id: str) -> None:
    """Best-effort recursive delete of one guest's directory - used by the
    startup expiry sweep (see guest_service.cleanup_expired). Never raises
    on a missing directory; any other OS error is swallowed since this is
    cleanup, not a user-facing action."""
    try:
        _validate_guest_id(guest_id)
    except InvalidPathError:
        return
    target = _guests_root() / guest_id
    try:
        shutil.rmtree(target, ignore_errors=True)
    except OSError:
        pass
