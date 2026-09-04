"""Safe, platform-specific "reveal in file manager" helpers.

Only ever opens a path the caller already owns (a completed download's own
file or its containing folder) via argument-array subprocess calls. Never
concatenates paths into a shell string and never accepts arbitrary commands.

Every path is additionally checked against `ensure_path_permitted` before any
filesystem action runs — even though the FastAPI/CORS layer already restricts
who can reach these endpoints in the first place. For an authenticated
(commercial) caller, this means confined strictly to
<DOWNLOAD_ROOT>/<user_id>/ (see user_storage_service.py) — no global
download_dir fallback, no cross-account history fallback. The
no-user_id branch below is the personal/local-mode-only fallback (kept
for backward compatibility with any programmatic caller that has no
authenticated user context) and is unreachable from any HTTP route in
this build, since every /api/fs/* and /api/history/* route requires auth
and always passes its own user_id.
"""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Optional

from app.config.logging_config import get_logger
from app.utils.exceptions import InvalidPathError
from app.utils.paths import is_within

logger = get_logger("filesystem")


def _open_with_os_handler(path: Path) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(path)], check=False)
    elif system == "Windows":
        subprocess.run(["explorer", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def ensure_path_permitted(path: Path, user_id: Optional[str] = None) -> None:
    """Raise InvalidPathError unless `path` is allowed for this caller.

    With a user_id (every real HTTP caller in this build), confined
    strictly to that user's own <DOWNLOAD_ROOT>/<user_id>/ directory - see
    user_storage_service.ensure_within_user_dir. Without one, falls back to
    the legacy personal-mode behavior (current global download_dir, or a
    file recorded in - unscoped - history), kept only for callers with no
    authenticated user context at all."""
    if user_id is not None:
        from app.services.user_storage_service import ensure_within_user_dir

        ensure_within_user_dir(path, user_id)
        return

    from app.database import history_repo
    from app.services.settings_service import get_settings

    download_dir = Path(get_settings().download_dir).expanduser().resolve()
    if is_within(path, download_dir):
        return
    if history_repo.filepath_exists(str(path)):
        return
    raise InvalidPathError("This path is outside the allowed download location.")


def open_path(raw_path: str, user_id: Optional[str] = None) -> None:
    """Open a file (in its default app) or a folder (in the file manager)."""
    path = Path(raw_path).expanduser().resolve()
    ensure_path_permitted(path, user_id=user_id)
    if not path.exists():
        raise InvalidPathError("That file or folder no longer exists.")
    _open_with_os_handler(path)
    logger.info("Opened path in system file manager")


def open_containing_folder(raw_path: str, user_id: Optional[str] = None) -> None:
    path = Path(raw_path).expanduser().resolve()
    target = path.parent if path.is_file() else path
    ensure_path_permitted(target, user_id=user_id)
    if not target.exists():
        raise InvalidPathError("That folder no longer exists.")
    _open_with_os_handler(target)
    logger.info("Opened containing folder in system file manager")
