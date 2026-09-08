import socket

import pytest

from app.utils.exceptions import UnsupportedUrlError
from app.utils.outbound_url import assert_public_http_url


def _resolver(address: str):
    return lambda *_args: [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.4", "169.254.169.254", "::1", "fc00::1"])
def test_rejects_private_and_metadata_destinations(address):
    with pytest.raises(UnsupportedUrlError):
        assert_public_http_url("https://media.example/file.jpg", resolver=_resolver(address))


def test_accepts_public_destination():
    assert_public_http_url("https://media.example/file.jpg", resolver=_resolver("93.184.216.34"))


@pytest.mark.parametrize(
    "url",
    [
        "https://media.example/file.jpg",
        "https://media.example:443/file.jpg",
        "http://media.example/file.jpg",
        "http://media.example:80/file.jpg",
    ],
)
def test_accepts_default_web_ports(url):
    assert_public_http_url(url, resolver=_resolver("93.184.216.34"))


@pytest.mark.parametrize("url", ["https://media.example:8443/file.jpg", "http://media.example:8080/file.jpg"])
def test_rejects_nonstandard_web_ports(url):
    with pytest.raises(UnsupportedUrlError):
        assert_public_http_url(url, resolver=_resolver("93.184.216.34"))


def test_rejects_credentials_and_non_http_schemes():
    with pytest.raises(UnsupportedUrlError):
        assert_public_http_url("https://user:secret@media.example/file.jpg", resolver=_resolver("93.184.216.34"))
    with pytest.raises(UnsupportedUrlError):
        assert_public_http_url("file:///etc/passwd", resolver=_resolver("93.184.216.34"))


def test_enforces_platform_host_allowlist():
    with pytest.raises(UnsupportedUrlError):
        assert_public_http_url(
            "https://attacker.example/redirect", allowed_hosts={"www.tiktok.com"}, resolver=_resolver("93.184.216.34")
        )
