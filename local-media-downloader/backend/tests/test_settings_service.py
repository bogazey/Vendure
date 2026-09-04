import pytest

from app.services.settings_service import get_settings, update_settings
from app.models.schemas import UpdateSettingsRequest


class TestSettingsPersistence:
    def test_defaults_when_nothing_stored(self):
        settings = get_settings()
        assert settings.max_concurrent_downloads == 2
        assert settings.theme == "system"

    def test_update_persists_and_reloads(self, tmp_path):
        update_settings(UpdateSettingsRequest(download_dir=str(tmp_path), max_concurrent_downloads=4))
        reloaded = get_settings()
        assert reloaded.max_concurrent_downloads == 4
        assert reloaded.download_dir == str(tmp_path.resolve())

    def test_partial_update_preserves_other_fields(self, tmp_path):
        update_settings(UpdateSettingsRequest(download_dir=str(tmp_path)))
        update_settings(UpdateSettingsRequest(mp3_bitrate=320))
        reloaded = get_settings()
        assert reloaded.mp3_bitrate == 320
        assert reloaded.download_dir == str(tmp_path.resolve())

    def test_invalid_download_dir_raises(self):
        with pytest.raises(ValueError):
            update_settings(UpdateSettingsRequest(download_dir=""))

    def test_theme_round_trips(self, tmp_path):
        update_settings(UpdateSettingsRequest(download_dir=str(tmp_path), theme="dark"))
        assert get_settings().theme == "dark"
