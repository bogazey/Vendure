"""Network destination validation for server-side HTTP fetches.

This is a defense-in-depth guard for URLs obtained from extractors and public
page metadata. Every request and redirect destination must be checked before
the HTTP client connects.
"""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlparse

from app.utils.exceptions import UnsupportedUrlError


def _is_public(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


def assert_public_http_url(
    url: str,
    *,
    allowed_hosts: set[str] | None = None,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> None:
    """Reject non-HTTP and non-public destinations before an outbound fetch."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise UnsupportedUrlError("That media URL is not safe to fetch.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsupportedUrlError("That media URL is not safe to fetch.") from exc
    expected_port = 80 if parsed.scheme == "http" else 443
    if port is not None and port != expected_port:
        raise UnsupportedUrlError("That media URL uses an unsupported network port.")
    if allowed_hosts is not None and host not in allowed_hosts:
        raise UnsupportedUrlError("That redirect left the supported media platform.")

    try:
        addresses = {item[4][0].split("%", 1)[0] for item in resolver(host, port or expected_port)}
    except (OSError, UnicodeError) as exc:
        raise UnsupportedUrlError("That media host could not be resolved.") from exc
    if not addresses or any(not _is_public(address) for address in addresses):
        raise UnsupportedUrlError("That media URL points to a private or restricted network.")
