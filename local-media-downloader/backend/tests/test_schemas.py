import pytest
from pydantic import ValidationError

from app.models.schemas import ClipRange, CreateDownloadRequest


class TestClipRangeValidation:
    def test_valid_clip_range(self):
        clip = ClipRange(start="00:10", end="00:30")
        assert clip.start == "00:10"

    def test_rejects_malformed_start(self):
        with pytest.raises(ValidationError):
            ClipRange(start="not-a-time", end="00:30")

    def test_rejects_malformed_end(self):
        with pytest.raises(ValidationError):
            ClipRange(start="00:10", end="garbage")


class TestCreateDownloadRequestValidation:
    def test_minimal_valid_request(self):
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123")
        assert request.media_type == "video"
        assert request.quality_key == "best"
        assert request.playlist_mode == "single"

    def test_rejects_empty_url(self):
        with pytest.raises(ValidationError):
            CreateDownloadRequest(url="")

    def test_rejects_overly_long_url(self):
        with pytest.raises(ValidationError):
            CreateDownloadRequest(url="https://example.com/" + "a" * 3000)

    def test_strips_whitespace_from_url(self):
        request = CreateDownloadRequest(url="  https://www.youtube.com/watch?v=abc123  ")
        assert request.url == "https://www.youtube.com/watch?v=abc123"

    def test_accepts_embedded_clip_range(self):
        request = CreateDownloadRequest(
            url="https://www.youtube.com/watch?v=abc123",
            clip={"start": "00:00", "end": "00:10"},
        )
        assert request.clip is not None
        assert request.clip.start == "00:00"

    def test_rejects_invalid_embedded_clip_range(self):
        with pytest.raises(ValidationError):
            CreateDownloadRequest(
                url="https://www.youtube.com/watch?v=abc123",
                clip={"start": "bad", "end": "00:10"},
            )
