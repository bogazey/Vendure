"""SSO / OIDC: authorization code + PKCE issuance and exchange."""
from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

from app.database.models import Product, User
from app.services import oidc_service


def _pkce_pair():
    verifier = secrets.token_urlsafe(64)[:64]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _make_product_and_client(db_session, product_id: str, redirect_uri: str):
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id.title(), domain=f"{product_id}.example", status="live"))
        db_session.flush()
    actor = User(email=f"bootstrap-{product_id}@example.com", password_hash="x", email_verified=True)
    db_session.add(actor)
    db_session.flush()
    client_obj, secret = oidc_service.register_client(
        db_session, actor, client_id=f"client-{product_id}", name=product_id, product_id=product_id,
        redirect_uris=[redirect_uri],
    )
    db_session.commit()
    return client_obj.client_id, secret


def _signed_in_user(client, email: str) -> None:
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 201


def test_authorize_rejects_unknown_client(client, db_session):
    verifier, challenge = _pkce_pair()
    _signed_in_user(client, "sso1@example.com")
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": "does-not-exist",
            "redirect_uri": "http://localhost:9999/callback", "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "rejected" in r.text.lower()


def test_authorize_rejects_unregistered_redirect_uri(client, db_session):
    client_id, _secret = _make_product_and_client(db_session, "sso-a", "http://localhost:9101/callback")
    verifier, challenge = _pkce_pair()
    _signed_in_user(client, "sso2@example.com")
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id,
            "redirect_uri": "http://evil.example/callback", "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_authorize_requires_pkce_s256(client, db_session):
    client_id, _secret = _make_product_and_client(db_session, "sso-b", "http://localhost:9102/callback")
    _signed_in_user(client, "sso3@example.com")
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id,
            "redirect_uri": "http://localhost:9102/callback", "code_challenge": "abc",
            "code_challenge_method": "plain",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_authorize_redirects_to_login_when_unauthenticated(client, db_session):
    client_id, _secret = _make_product_and_client(db_session, "sso-c", "http://localhost:9103/callback")
    verifier, challenge = _pkce_pair()
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id,
            "redirect_uri": "http://localhost:9103/callback", "code_challenge": challenge,
            "code_challenge_method": "S256", "state": "xyz",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"].startswith("/login?next=")


def test_full_authorization_code_pkce_exchange(client, db_session):
    client_id, secret = _make_product_and_client(db_session, "sso-d", "http://localhost:9104/callback")
    verifier, challenge = _pkce_pair()
    _signed_in_user(client, "sso4@example.com")

    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id,
            "redirect_uri": "http://localhost:9104/callback", "code_challenge": challenge,
            "code_challenge_method": "S256", "state": "my-state-123",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    parsed = urlparse(r.headers["location"])
    assert parsed.path == "/callback"
    query = parse_qs(parsed.query)
    assert query["state"] == ["my-state-123"]
    code = query["code"][0]

    token_r = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "client_secret": secret,
        "code": code, "redirect_uri": "http://localhost:9104/callback", "code_verifier": verifier,
    })
    assert token_r.status_code == 200
    body = token_r.json()
    assert "access_token" in body and "id_token" in body and "refresh_token" in body


def test_authorization_code_is_single_use(client, db_session):
    client_id, secret = _make_product_and_client(db_session, "sso-e", "http://localhost:9105/callback")
    verifier, challenge = _pkce_pair()
    _signed_in_user(client, "sso5@example.com")

    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id,
            "redirect_uri": "http://localhost:9105/callback", "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]

    ok = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "client_secret": secret,
        "code": code, "redirect_uri": "http://localhost:9105/callback", "code_verifier": verifier,
    })
    assert ok.status_code == 200

    replay = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "client_secret": secret,
        "code": code, "redirect_uri": "http://localhost:9105/callback", "code_verifier": verifier,
    })
    assert replay.status_code == 400
    assert replay.json()["code"] == "INVALID_GRANT"


def test_authorization_code_expiry_enforced(client, db_session, monkeypatch):
    from app.config.settings import get_settings

    monkeypatch.setattr(get_settings(), "authorization_code_ttl_seconds", 0)
    client_id, secret = _make_product_and_client(db_session, "sso-f", "http://localhost:9106/callback")
    verifier, challenge = _pkce_pair()
    _signed_in_user(client, "sso6@example.com")

    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id,
            "redirect_uri": "http://localhost:9106/callback", "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]

    import time
    time.sleep(0.01)

    result = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "client_secret": secret,
        "code": code, "redirect_uri": "http://localhost:9106/callback", "code_verifier": verifier,
    })
    assert result.status_code == 400


def test_wrong_client_id_rejected_at_token_exchange(client, db_session):
    client_a, secret_a = _make_product_and_client(db_session, "sso-g", "http://localhost:9107/callback")
    client_b, secret_b = _make_product_and_client(db_session, "sso-h", "http://localhost:9108/callback")
    verifier, challenge = _pkce_pair()
    _signed_in_user(client, "sso7@example.com")

    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_a,
            "redirect_uri": "http://localhost:9107/callback", "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]

    # Client B tries to redeem client A's code with its own credentials.
    result = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_b, "client_secret": secret_b,
        "code": code, "redirect_uri": "http://localhost:9107/callback", "code_verifier": verifier,
    })
    assert result.status_code in (400, 401)


def test_pkce_verifier_mismatch_rejected(client, db_session):
    client_id, secret = _make_product_and_client(db_session, "sso-i", "http://localhost:9109/callback")
    verifier, challenge = _pkce_pair()
    _signed_in_user(client, "sso8@example.com")

    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id,
            "redirect_uri": "http://localhost:9109/callback", "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]

    wrong_verifier, _ = _pkce_pair()
    result = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "client_secret": secret,
        "code": code, "redirect_uri": "http://localhost:9109/callback", "code_verifier": wrong_verifier,
    })
    assert result.status_code == 400
    assert result.json()["code"] == "INVALID_GRANT"


def test_access_token_audience_is_pinned_to_client(client, db_session):
    """A token minted for client A must not verify against client B's
    expected audience (mission-brief section 24: cross-product token misuse)."""
    from app.security.jwt_tokens import decode_oidc_access_token

    client_a, secret_a = _make_product_and_client(db_session, "sso-j", "http://localhost:9110/callback")
    verifier, challenge = _pkce_pair()
    _signed_in_user(client, "sso9@example.com")

    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_a,
            "redirect_uri": "http://localhost:9110/callback", "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    token_r = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_a, "client_secret": secret_a,
        "code": code, "redirect_uri": "http://localhost:9110/callback", "code_verifier": verifier,
    })
    access_token = token_r.json()["access_token"]

    assert decode_oidc_access_token(access_token, expected_audience=client_a) is not None
    assert decode_oidc_access_token(access_token, expected_audience="some-other-client") is None


def test_userinfo_requires_bearer_token(client):
    r = client.get("/oauth/userinfo")
    assert r.status_code == 401


def test_jwks_never_exposes_private_key(client):
    r = client.get("/.well-known/jwks.json")
    body = r.json()
    keys = "".join(str(v) for v in body["keys"][0].values())
    assert "PRIVATE KEY" not in keys
    assert set(body["keys"][0].keys()) == {"kty", "use", "alg", "kid", "n", "e"}
