"""Unit tests for the pure (non-network) parts of the SDK."""
from __future__ import annotations

import base64
import hashlib

import httpx
import pytest

from platform_client import PlatformClient, generate_pkce_pair
from platform_client.client import PlatformClientError


def test_pkce_pair_challenge_matches_verifier():
    verifier, challenge = generate_pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected
    assert len(verifier) == 64


def test_pkce_pairs_are_unique():
    pairs = {generate_pkce_pair() for _ in range(20)}
    assert len(pairs) == 20


def _client() -> PlatformClient:
    return PlatformClient(
        base_url="https://auth.example.test", client_id="demo-client", client_secret="s3cr3t",
        redirect_uri="https://product.example.test/callback",
    )


def test_authorize_url_is_well_formed_and_never_carries_the_client_secret():
    client = _client()
    url = client.authorize_url(state="xyz", code_challenge="abc123")
    assert url.startswith("https://auth.example.test/oauth/authorize?")
    assert "response_type=code" in url
    assert "client_id=demo-client" in url
    assert "code_challenge_method=S256" in url
    assert "s3cr3t" not in url  # the whole point of PKCE - no secret in a browser-facing URL


def test_exchange_code_requires_a_client_secret():
    public_client = PlatformClient(base_url="https://auth.example.test", client_id="public-client")
    with pytest.raises(PlatformClientError):
        public_client.exchange_code(code="x", code_verifier="y")


def test_get_service_token_requires_a_client_secret():
    public_client = PlatformClient(base_url="https://auth.example.test", client_id="public-client")
    with pytest.raises(PlatformClientError):
        public_client.get_service_token()


def test_has_capability_boolean():
    result = {"capabilities": {"ads.enabled": True, "watermark.enabled": False}}
    assert PlatformClient.has_capability(result, "ads.enabled") is True
    assert PlatformClient.has_capability(result, "watermark.enabled") is False
    assert PlatformClient.has_capability(result, "does.not.exist") is False


def test_has_capability_integer_at_least():
    result = {"capabilities": {"download.max_resolution": 720}}
    assert PlatformClient.has_capability(result, "download.max_resolution", at_least=480) is True
    assert PlatformClient.has_capability(result, "download.max_resolution", at_least=1080) is False


def test_has_capability_unlimited_sentinel_satisfies_any_at_least():
    result = {"capabilities": {"download.max_resolution": -1}}
    assert PlatformClient.has_capability(result, "download.max_resolution", at_least=999999) is True


def test_exchange_code_uses_injected_http_client_and_never_touches_the_network():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/oauth/token"
        form = dict(x.split("=") for x in request.content.decode().split("&"))
        assert form["grant_type"] == "authorization_code"
        assert form["client_id"] == "demo-client"
        return httpx.Response(200, json={"access_token": "at", "id_token": "it", "refresh_token": "rt", "expires_in": 900})

    transport = httpx.MockTransport(handler)
    fake_http_client = httpx.Client(transport=transport)

    client = _client()
    tokens = client.exchange_code(code="c", code_verifier="v", http_client=fake_http_client)
    assert tokens.access_token == "at"
    assert tokens.id_token == "it"
    assert tokens.expires_in == 900


def test_get_my_entitlement_sends_bearer_header():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"entitled": True, "entitlement": {"plan_slug": "pro"}})

    fake_http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = _client()
    result = client.get_my_entitlement("my-access-token", http_client=fake_http_client)
    assert captured["auth"] == "Bearer my-access-token"
    assert result["entitled"] is True
