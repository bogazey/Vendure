"""Safe, platform-specific "reveal in file manager" helpers.

Only ever opens a path the caller already owns (a completed download's own
file or its containing folder) via argument-array subprocess calls. Never
concatenates paths into a shell string and never accepts arbitrary commands.

Every path is additionally checked against `ensure_path_permitted` before any
filesystem action runs, so this can never be used to open or delete a path
outside the configured download folder (or, for legacy files, a path we
actually recorded in history) — even though the FastAPI/CORS layer already
restricts who can reach these endpoints in the first place.
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
    """Raise InvalidPathError unless `path` is inside the current download
    folder, or matches a file `user_id` themselves actually downloaded
    (recorded in their own history rows) - the history fallback is always
    user-scoped so this can never be used to probe or act on another
    account's downloaded files, even though download_dir itself is still a
    shared, global setting today (see COMMERCIAL_ARCHITECTURE.md §4.1)."""
    from app.database import history_repo
    from app.services.settings_service import get_settings

    download_dir = Path(get_settings().download_dir).expanduser().resolve()
    if is_within(path, download_dir):
        return
    if history_repo.filepath_exists(str(path), user_id=user_id):
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
