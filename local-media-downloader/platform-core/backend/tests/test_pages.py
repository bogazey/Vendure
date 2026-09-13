"""The hosted /login and /signup pages: `next` must survive the login <->
signup switch-link round trip. Caught by a real browser run (see
docs/platform/SSO.md) - an earlier version HTML-escaped `next` for the
`<a href>` instead of URL-encoding it, so the browser reparsed the
embedded `&client_id=...&code_challenge=...` as this page's OWN query
string instead of part of the `next` value, silently losing the pending
authorize request.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


def _extract_switch_href(html: str) -> str:
    match = re.search(r'<a href="([^"]+)">(?:Create one|Sign in)</a>', html)
    assert match, html
    return match.group(1)


def test_login_page_switch_link_preserves_full_next_value(client, db_session):
    from app.database.models import Product
    from app.services import oidc_service
    from app.database.models import User

    db_session.add(Product(id="pages-demo", name="Pages Demo", domain="pages-demo.example", status="live"))
    db_session.flush()
    bootstrap = User(email="pages-bootstrap@example.com", password_hash="x", email_verified=True)
    db_session.add(bootstrap)
    db_session.flush()
    oidc_service.register_client(
        db_session, bootstrap, "pages-client", "Pages Demo", "pages-demo",
        ["http://localhost:9999/callback"],
    )
    db_session.commit()

    authorize_query = (
        "response_type=code&client_id=pages-client&redirect_uri=http%3A%2F%2Flocalhost%3A9999%2Fcallback"
        "&scope=openid+profile&state=abc123&code_challenge=xyz&code_challenge_method=S256"
    )
    next_value = f"/oauth/authorize?{authorize_query}"

    r = client.get("/login", params={"next": next_value})
    assert r.status_code == 200
    href = _extract_switch_href(r.text)
    assert href.startswith("/signup?next=")

    # The href's `next` query param, once URL-decoded, must reconstruct the
    # exact original path+query - not be truncated at the first `&`.
    parsed = urlparse(href)
    recovered = parse_qs(parsed.query)["next"][0]
    assert recovered == next_value

    # And the inline JS redirect target must be the same full value too.
    assert f'"{next_value}"' in r.text


def test_signup_page_switch_link_preserves_full_next_value(client):
    next_value = "/oauth/authorize?response_type=code&client_id=x&redirect_uri=http%3A%2F%2Fa%2Fb&code_challenge=y&code_challenge_method=S256"
    r = client.get("/signup", params={"next": next_value})
    assert r.status_code == 200
    href = _extract_switch_href(r.text)
    parsed = urlparse(href)
    recovered = parse_qs(parsed.query)["next"][0]
    assert recovered == next_value


def test_next_outside_oauth_authorize_is_rejected():
    from app.api.routes_pages import _safe_next

    assert _safe_next("https://evil.example/steal") == "/"
    assert _safe_next("/some/other/path") == "/"
    assert _safe_next(None) == "/"
    assert _safe_next("/oauth/authorize?client_id=x") == "/oauth/authorize?client_id=x"
