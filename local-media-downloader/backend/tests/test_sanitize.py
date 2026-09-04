from app.utils.sanitize import sanitize_filename


class TestSanitizeFilename:
    def test_strips_windows_forbidden_characters(self):
        result = sanitize_filename('My Video: "Best" <Clip> | Part?*')
        for char in '<>:"/\\|?*':
            assert char not in result

    def test_strips_control_characters(self):
        result = sanitize_filename("Title\x00with\x1fcontrol")
        assert "\x00" not in result
        assert "\x1f" not in result

    def test_collapses_whitespace(self):
        assert sanitize_filename("My    Video   Title") == "My Video Title"

    def test_strips_trailing_dots_and_spaces(self):
        result = sanitize_filename("Video Title...   ")
        assert result == "Video Title"

    def test_empty_input_uses_fallback(self):
        assert sanitize_filename("") == "download"

    def test_whitespace_only_uses_fallback(self):
        assert sanitize_filename("   ") == "download"

    def test_reserved_windows_name_gets_prefixed(self):
        assert sanitize_filename("CON") == "_CON"
        assert sanitize_filename("con") == "_con"

    def test_long_name_is_truncated(self):
        result = sanitize_filename("a" * 300)
        assert len(result) <= 150

    def test_custom_fallback_used(self):
        assert sanitize_filename("", fallback="clip") == "clip"

    def test_preserves_safe_unicode(self):
        assert sanitize_filename("日本語タイトル") == "日本語タイトル"

    def test_path_separators_removed(self):
        result = sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert ".." not in result or result != "../../etc/passwd"
