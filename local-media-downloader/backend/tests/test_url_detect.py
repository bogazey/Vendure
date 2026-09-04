from app.models.enums import Platform
from app.utils.url_detect import (
    detect_platform,
    is_supported_platform,
    is_valid_url,
    looks_like_playlist_url,
)


class TestIsValidUrl:
    def test_accepts_https_url(self):
        assert is_valid_url("https://www.youtube.com/watch?v=abc123")

    def test_accepts_http_url(self):
        assert is_valid_url("http://youtu.be/abc123")

    def test_rejects_empty(self):
        assert not is_valid_url("")

    def test_rejects_non_url_text(self):
        assert not is_valid_url("not a url at all")

    def test_rejects_ftp_scheme(self):
        assert not is_valid_url("ftp://example.com/file")

    def test_rejects_javascript_scheme(self):
        assert not is_valid_url("javascript:alert(1)")

    def test_rejects_overly_long_url(self):
        assert not is_valid_url("https://example.com/" + "a" * 3000)


class TestDetectPlatform:
    def test_youtube_watch(self):
        assert detect_platform("https://www.youtube.com/watch?v=abc123") == Platform.YOUTUBE

    def test_youtube_short_link(self):
        assert detect_platform("https://youtu.be/abc123") == Platform.YOUTUBE

    def test_youtube_shorts(self):
        assert detect_platform("https://www.youtube.com/shorts/abc123") == Platform.YOUTUBE

    def test_tiktok(self):
        assert detect_platform("https://www.tiktok.com/@user/video/123") == Platform.TIKTOK

    def test_tiktok_short_link(self):
        assert detect_platform("https://vm.tiktok.com/abc123") == Platform.TIKTOK

    def test_instagram_reel(self):
        assert detect_platform("https://www.instagram.com/reel/abc123/") == Platform.INSTAGRAM

    def test_facebook_watch(self):
        assert detect_platform("https://www.facebook.com/watch/?v=123") == Platform.FACEBOOK

    def test_facebook_short_link(self):
        assert detect_platform("https://fb.watch/abc123") == Platform.FACEBOOK

    def test_unsupported_domain(self):
        assert detect_platform("https://vimeo.com/12345") == Platform.UNKNOWN

    def test_invalid_url_is_unknown(self):
        assert detect_platform("not a url") == Platform.UNKNOWN


class TestSupportedPlatform:
    def test_youtube_is_supported(self):
        assert is_supported_platform(Platform.YOUTUBE)

    def test_unknown_is_not_supported(self):
        assert not is_supported_platform(Platform.UNKNOWN)


class TestPlaylistDetection:
    def test_detects_list_param(self):
        assert looks_like_playlist_url("https://www.youtube.com/watch?v=abc&list=PLxyz")

    def test_no_list_param(self):
        assert not looks_like_playlist_url("https://www.youtube.com/watch?v=abc")
