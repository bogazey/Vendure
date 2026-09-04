import pytest

from app.utils.timecode import parse_timecode, validate_clip_range


class TestParseTimecode:
    def test_mm_ss(self):
        assert parse_timecode("02:30") == 150

    def test_hh_mm_ss(self):
        assert parse_timecode("01:02:03") == 3723

    def test_zero(self):
        assert parse_timecode("00:00") == 0

    def test_strips_whitespace(self):
        assert parse_timecode("  01:00  ") == 60

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_timecode("not a time")

    def test_invalid_seconds_raises(self):
        with pytest.raises(ValueError):
            parse_timecode("00:99")

    def test_missing_colon_raises(self):
        with pytest.raises(ValueError):
            parse_timecode("12345")


class TestValidateClipRange:
    def test_valid_range(self):
        start, end = validate_clip_range("00:10", "00:30")
        assert start == 10
        assert end == 30

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError):
            validate_clip_range("00:30", "00:10")

    def test_equal_start_end_raises(self):
        with pytest.raises(ValueError):
            validate_clip_range("00:10", "00:10")
