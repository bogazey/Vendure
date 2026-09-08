"""Public metadata fallback for TikTok photo/carousel posts."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import httpx

from app.utils.exceptions import NetworkError, NoDownloadableMediaError, UnavailableMediaError

_PHOTO_PATH_RE = re.compile(r"/(?:@[^/]+/)?photo/(\d+)(?:/|$)")
_TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}
_SHORT_HOSTS = {"vm.tiktok.com", "vt.tiktok.com"}
_USER_AGENT = "Mozilla/5.0 (compatible; Loady/1.0; +https://loady.cc)"


class NotTikTokPhotoUrl(Exception):
    """A TikTok URL is not a direct or redirected photo post."""


class _JsonScripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._active_id: str | None = None
        self._chunks: list[str] = []
        self.scripts: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and (script_id := dict(attrs).get("id")):
            self._active_id, self._chunks = script_id, []

    def handle_data(self, data: str) -> None:
        if self._active_id:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._active_id:
            self.scripts[self._active_id] = "".join(self._chunks)
            self._active_id, self._chunks = None, []


def _is_tiktok_host(host: str | None) -> bool:
    return (host or "").lower().rstrip(".") in _TIKTOK_HOSTS


def is_photo_url(url: str) -> bool:
    parsed = urlparse(url)
    return _is_tiktok_host(parsed.hostname) and _PHOTO_PATH_RE.search(parsed.path) is not None


def is_short_url(url: str) -> bool:
    return (urlparse(url).hostname or "").lower().rstrip(".") in _SHORT_HOSTS


def _photo_id(url: str) -> str | None:
    match = _PHOTO_PATH_RE.search(urlparse(url).path)
    return match.group(1) if match else None


def _request(client: httpx.Client, url: str, retries: int) -> httpx.Response:
    attempts = max(1, min(retries + 1, 4))
    last_error: httpx.HTTPError | None = None
    for attempt in range(attempts):
        try:
            response = client.get(url, headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.8"})
            if response.is_redirect:
                return response
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt + 1 == attempts:
                break
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {429, 500, 502, 503, 504} or attempt + 1 == attempts:
                raise UnavailableMediaError(
                    "This TikTok photo post is unavailable or could not be accessed.",
                    technical=f"TikTok returned HTTP {exc.response.status_code}.",
                ) from exc
            last_error = exc
    raise NetworkError(
        "A network error occurred while contacting TikTok. Check your connection and try again.",
        technical=type(last_error).__name__ if last_error else None,
    ) from last_error


def _resolve_short_url(client: httpx.Client, url: str, retries: int) -> str:
    current = url
    for _ in range(6):
        parsed = urlparse(current)
        if parsed.scheme not in {"http", "https"} or not _is_tiktok_host(parsed.hostname):
            raise NotTikTokPhotoUrl()
        response = _request(client, current, retries)
        if not response.is_redirect:
            if is_photo_url(str(response.url)):
                return str(response.url)
            raise NotTikTokPhotoUrl()
        location = response.headers.get("location")
        if not location:
            raise NotTikTokPhotoUrl()
        current = urljoin(str(response.url), location)
    raise UnavailableMediaError("The TikTok short link redirected too many times.")


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _urls(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.startswith(("http://", "https://")) else []
    if isinstance(value, list):
        return [url for item in value for url in _urls(item)]
    if isinstance(value, dict):
        preferred = ("urlList", "url_list", "urls", "url")
        found = [url for key in preferred if key in value for url in _urls(value[key])]
        return found or [url for item in value.values() for url in _urls(item)]
    return []


def _image_records(node: dict[str, Any]) -> list[dict[str, Any]]:
    image_post = node.get("imagePostInfo") or node.get("imagePost") or node.get("image_post_info")
    if not isinstance(image_post, dict):
        return []
    records = image_post.get("displayImages") or image_post.get("images") or image_post.get("display_images")
    return [record for record in records or [] if isinstance(record, dict)]


def _normalized_info(data: Any, expected_id: str) -> dict[str, Any] | None:
    candidates = list(_walk_dicts(data))
    candidates.sort(
        key=lambda node: str((node.get("itemInfos") or node.get("itemStruct") or node).get("id", "")) == expected_id,
        reverse=True,
    )
    for node in candidates:
        records = _image_records(node)
        if not records:
            continue
        item = node.get("itemInfos") or node.get("itemStruct") or node
        author = node.get("authorInfos") or item.get("author") or node.get("author") or {}
        post_id = str(item.get("id") or node.get("id") or expected_id)
        if post_id != expected_id:
            continue
        description = item.get("text") or item.get("desc") or item.get("description") or node.get("description") or ""
        if isinstance(author, dict):
            uploader = author.get("uniqueId") or author.get("unique_id") or author.get("nickName") or author.get("nickname")
        else:
            uploader = author if isinstance(author, str) else None
        entries = []
        for index, record in enumerate(records, start=1):
            urls = _urls(record)
            if not urls:
                continue
            width = record.get("width") or record.get("imageWidth") or record.get("image_width")
            height = record.get("height") or record.get("imageHeight") or record.get("image_height")
            thumbnails = [{"url": image_url, "width": width, "height": height} for image_url in dict.fromkeys(urls)]
            entries.append({
                "id": f"{post_id}-{index}", "title": description or f"TikTok photo {index}",
                "uploader": uploader, "thumbnail": urls[0], "thumbnails": thumbnails, "formats": [],
                "http_headers": {"Referer": "https://www.tiktok.com/"},
            })
        if entries:
            return {
                "_type": "playlist", "id": post_id, "title": description or f"TikTok photo post {post_id}",
                "description": description or None, "uploader": uploader, "entries": entries,
            }
    return None


def extract_photo_info(url: str, *, timeout: int, retries: int) -> dict[str, Any]:
    """Return a yt-dlp-compatible playlist dict for a public photo post."""
    if not (is_photo_url(url) or is_short_url(url)):
        raise NotTikTokPhotoUrl()
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        resolved = _resolve_short_url(client, url, retries) if is_short_url(url) else url
        post_id = _photo_id(resolved)
        if not post_id:
            raise NotTikTokPhotoUrl()
        response = _request(client, f"https://www.tiktok.com/embed/v2/{post_id}", retries)

    parser = _JsonScripts()
    parser.feed(response.text)
    for script_id in ("__FRONTITY_CONNECT_STATE__", "__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE"):
        payload = parser.scripts.get(script_id)
        if not payload:
            continue
        try:
            info = _normalized_info(json.loads(payload), post_id)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if info:
            return info
    raise NoDownloadableMediaError(
        "This TikTok photo post does not contain publicly accessible images.",
        technical="TikTok public photo metadata was missing or malformed.",
    )
