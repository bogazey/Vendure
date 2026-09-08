"""TikTok public photo metadata parsing; every HTTP response is mocked."""
from __future__ import annotations

import json

import httpx
import pytest

from app.services import tiktok_photo_service
from app.utils.exceptions import NetworkError, NoDownloadableMediaError

PHOTO_URL = "https://www.tiktok.com/@creator/photo/7682896059135216916"
SHORT_URL = "https://vm.tiktok.com/ZMock/"


def _embed_html(images: list[dict] | None = None) -> str:
    video_data = {
        "itemInfos": {"id": "7682896059135216916", "text": "Four public photos"},
        "authorInfos": {"uniqueId": "creator", "nickName": "Creator"},
        "imagePostInfo": {"displayImages": images if images is not None else [
            {"width": 1080, "height": 1440, "urlList": ["https://cdn.example/one.webp"]},
            {"width": 1080, "height": 1440, "urlList": ["https://cdn.example/two.jpg"]},
        ]},
    }
    state = {"source": {"data": {"/embed/v2/7682896059135216916": {"videoData": video_data}}}}
    return '<script id="__FRONTITY_CONNECT_STATE__" type="application/json">' + json.dumps(state) + "</script>"


class FakeClient:
    responses: list[httpx.Response | Exception] = []
    calls: list[str] = []
    kwargs: dict = {}

    def __init__(self, **kwargs):
        FakeClient.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, url, **_kwargs):
        FakeClient.calls.append(url)
        result = FakeClient.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _response(status: int, url: str, *, text: str = "", location: str | None = None) -> httpx.Response:
    headers = {"location": location} if location else {}
    return httpx.Response(status, text=text, headers=headers, request=httpx.Request("GET", url))


@pytest.fixture(autouse=True)
def _mock_http(monkeypatch):
    monkeypatch.setattr(tiktok_photo_service.httpx, "Client", FakeClient)
    FakeClient.responses = []
    FakeClient.calls = []
    FakeClient.kwargs = {}


def test_direct_photo_url_returns_normalized_carousel():
    FakeClient.responses = [_response(200, "https://www.tiktok.com/embed/v2/7682896059135216916", text=_embed_html())]
    info = tiktok_photo_service.extract_photo_info(PHOTO_URL, timeout=17, retries=2)

    assert info["_type"] == "playlist"
    assert info["id"] == "7682896059135216916"
    assert info["title"] == "Four public photos"
    assert info["uploader"] == "creator"
    assert [entry["thumbnail"] for entry in info["entries"]] == [
        "https://cdn.example/one.webp", "https://cdn.example/two.jpg"
    ]
    assert info["entries"][0]["thumbnails"][0]["width"] == 1080
    assert FakeClient.kwargs == {"timeout": 17, "follow_redirects": False}


def test_short_url_is_safely_resolved_before_embed_fetch():
    direct = PHOTO_URL
    FakeClient.responses = [
        _response(302, SHORT_URL, location=direct),
        _response(200, direct, text="public detail page"),
        _response(200, "https://www.tiktok.com/embed/v2/7682896059135216916", text=_embed_html()),
    ]
    info = tiktok_photo_service.extract_photo_info(SHORT_URL, timeout=10, retries=0)
    assert info["id"] == "7682896059135216916"
    assert FakeClient.calls[-1].endswith("/embed/v2/7682896059135216916")


def test_multi_image_carousel_preserves_every_image_and_dimensions():
    images = [
        {"width": 720 + i, "height": 1280 + i, "urlList": [f"https://cdn.example/{i}.jpeg"]}
        for i in range(5)
    ]
    FakeClient.responses = [_response(200, "https://www.tiktok.com/embed/v2/7682896059135216916", text=_embed_html(images))]
    info = tiktok_photo_service.extract_photo_info(PHOTO_URL, timeout=10, retries=0)
    assert len(info["entries"]) == 5
    assert info["entries"][4]["thumbnails"][0] == {
        "url": "https://cdn.example/4.jpeg", "width": 724, "height": 1284
    }


@pytest.mark.parametrize("html", ["<html></html>", '<script id="__FRONTITY_CONNECT_STATE__">not json</script>'])
def test_missing_or_malformed_metadata_is_friendly(html):
    FakeClient.responses = [_response(200, "https://www.tiktok.com/embed/v2/7682896059135216916", text=html)]
    with pytest.raises(NoDownloadableMediaError) as exc_info:
        tiktok_photo_service.extract_photo_info(PHOTO_URL, timeout=10, retries=0)
    assert "publicly accessible images" in exc_info.value.message


def test_network_failure_is_retried_and_classified():
    request = httpx.Request("GET", "https://www.tiktok.com/embed/v2/7682896059135216916")
    FakeClient.responses = [httpx.ConnectError("offline", request=request)] * 3
    with pytest.raises(NetworkError):
        tiktok_photo_service.extract_photo_info(PHOTO_URL, timeout=10, retries=2)
    assert len(FakeClient.calls) == 3
