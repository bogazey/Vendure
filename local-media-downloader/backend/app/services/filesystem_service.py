"""Safe, platform-specific "reveal in file manager" helpers.

Only ever opens a path the caller already owns (a completed download's own
file or its containing folder) via argument-array subprocess calls. Never
concatenates paths into a shell string and never accepts arbitrary commands.
"""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from app.config.logging_config import get_logger
from app.utils.exceptions import InvalidPathError

logger = get_logger("filesystem")


def _open_with_os_handler(path: Path) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(path)], check=False)
    elif system == "Windows":
        subprocess.run(["explorer", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def open_path(raw_path: str) -> None:
    """Open a file (in its default app) or a folder (in the file manager)."""
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise InvalidPathError("That file or folder no longer exists.")
    _open_with_os_handler(path)
    logger.info("Opened path in system file manager")


def open_containing_folder(raw_path: str) -> None:
    path = Path(raw_path).expanduser().resolve()
    target = path.parent if path.is_file() else path
    if not target.exists():
        raise InvalidPathError("That folder no longer exists.")
    _open_with_os_handler(target)
    logger.info("Opened containing folder in system file manager")
