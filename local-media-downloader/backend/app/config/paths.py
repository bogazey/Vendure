"""Central, environment-driven filesystem locations.

All paths derive from the project root (three levels up from this file) unless
overridden by environment variables, so nothing here hardcodes a personal path.
"""
from __future__ import annotations

import os
from pathlib import Path

# backend/app/config/paths.py -> local-media-downloader/
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = Path(os.environ.get("LMD_DATA_DIR", PROJECT_ROOT / "data")).resolve()
LOG_DIR = Path(os.environ.get("LMD_LOG_DIR", DATA_DIR / "logs")).resolve()
DB_PATH = Path(os.environ.get("LMD_DB_PATH", DATA_DIR / "app.db")).resolve()
DEFAULT_DOWNLOAD_DIR = Path(
    os.environ.get("LMD_DOWNLOAD_DIR", PROJECT_ROOT / "downloads")
).resolve()

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
