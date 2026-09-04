"""Safe path validation helpers.

Guards against path traversal and validates that a chosen directory is usable
as a download destination. Never used to expose arbitrary file reads.
"""
from __future__ import annotations

import os
from pathlib import Path


def resolve_safe_directory(raw_path: str) -> Path:
    """Expand and resolve a user-supplied directory path.

    Raises ValueError on empty input. Does not restrict to any parent root
    since the user explicitly chooses their own download directory, but does
    normalize `~` and relative segments to an absolute, canonical path.
    """
    if not raw_path or not raw_path.strip():
        raise ValueError("Path must not be empty.")
    expanded = os.path.expanduser(raw_path.strip())
    return Path(expanded).resolve()


def validate_directory_writable(path: Path) -> tuple[bool, str | None]:
    """Return (ok, reason). Creates the directory if it does not yet exist."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        return False, "Permission denied creating this folder."
    except OSError as exc:
        return False, f"Could not create folder: {exc}"

    if not path.is_dir():
        return False, "Path exists but is not a directory."

    probe = path / ".lmd_write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except PermissionError:
        return False, "Folder is not writable."
    except OSError as exc:
        return False, f"Folder is not writable: {exc}"

    return True, None


def is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
