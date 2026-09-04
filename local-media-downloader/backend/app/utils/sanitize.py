"""Filename sanitization safe for Windows, macOS, and Linux filesystems."""
from __future__ import annotations

import re

# Characters forbidden on Windows, plus control characters.
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_MAX_COMPONENT_LENGTH = 150


def sanitize_filename(name: str, fallback: str = "download") -> str:
    """Strip unsafe characters and normalize length/whitespace for a filename component."""
    if not name:
        return fallback

    cleaned = _FORBIDDEN.sub("_", name)
    cleaned = cleaned.replace("\n", " ").replace("\r", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.strip(". ")  # trailing dots/spaces are unsafe on Windows

    if not cleaned:
        return fallback

    if cleaned.upper() in _RESERVED_WINDOWS_NAMES:
        cleaned = f"_{cleaned}"

    if len(cleaned) > _MAX_COMPONENT_LENGTH:
        cleaned = cleaned[:_MAX_COMPONENT_LENGTH].rstrip()

    return cleaned or fallback
