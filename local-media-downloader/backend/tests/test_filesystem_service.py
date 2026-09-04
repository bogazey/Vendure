"""Path-permission guard: opening/deleting files must stay inside the
configured download folder, or be a path we actually recorded in history."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.database import history_repo
from app.models.schemas import UpdateSettingsRequest
from app.services import filesystem_service
from app.services.settings_service import update_settings
from app.utils.exceptions import InvalidPathError


@pytest.fixture()
def download_dir(tmp_path):
    d = tmp_path / "downloads"
    d.mkdir()
    update_settings(UpdateSettingsRequest(download_dir=str(d)))
    return d


class TestEnsurePathPermitted:
    def test_allows_path_inside_download_dir(self, download_dir):
        target = download_dir / "clip [abc123].mp4"
        target.write_text("data")
        filesystem_service.ensure_path_permitted(target)  # must not raise

    def test_allows_download_dir_itself(self, download_dir):
        filesystem_service.ensure_path_permitted(download_dir)  # must not raise

    def test_rejects_path_outside_download_dir(self, download_dir, tmp_path):
        outsider = tmp_path / "not-a-download" / "secret.txt"
        outsider.parent.mkdir()
        outsider.write_text("data")
        with pytest.raises(InvalidPathError):
            filesystem_service.ensure_path_permitted(outsider)

    def test_allows_legacy_file_recorded_in_history(self, download_dir, tmp_path):
        old_download_dir = tmp_path / "old-downloads"
        old_download_dir.mkdir()
        old_file = old_download_dir / "old-clip [xyz789].mp4"
        old_file.write_text("data")

        history_repo.upsert(
            {
                "id": str(uuid.uuid4()),
                "url": "https://www.youtube.com/watch?v=xyz789",
                "platform": "youtube",
                "title": "Old Clip",
                "uploader": None,
                "thumbnail": None,
                "format_label": "1080p",
                "resolution": "1080p",
                "filepath": str(old_file),
                "filesize": 4,
                "created_at": "2026-01-01T00:00:00+00:00",
                "completed_at": "2026-01-01T00:01:00+00:00",
                "status": "completed",
                "error_message": None,
            }
        )

        # download_dir has since changed (fixture above), but the file is
        # still openable/removable because we recorded it ourselves.
        filesystem_service.ensure_path_permitted(old_file)  # must not raise

    def test_rejects_unknown_path_even_if_plausible(self, download_dir, tmp_path):
        unknown = tmp_path / "random" / "not-ours.mp4"
        unknown.parent.mkdir()
        unknown.write_text("data")
        with pytest.raises(InvalidPathError):
            filesystem_service.ensure_path_permitted(unknown)
