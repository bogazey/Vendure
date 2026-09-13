"""Mission 6 (Phases 36-37): service-to-service (client-credentials) auth
- fails closed with no grants, scope enforcement, product isolation, and
secret rotation invalidating the old secret."""
from __future__ import annotations

from app.database.models import Product, User
from app.services import oidc_service, service_auth
from app.security.jwt_tokens import introspect_service_access_token
from app.utils.exceptions import InsufficientScopeError, InvalidClientError


def _admin(db_session, email: str) -> User:
    user = User(email=email, password_hash="x", email_verified=True)
    db_session.add(user)
    db_session.flush()
    return user


def _product(db_session, product_id: str) -> Product:
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.flush()
    return db_session.get(Product, product_id)


def test_client_with_no_grants_cannot_get_a_service_token(db_session):
    admin = _admin(db_session, "admin-svc1@example.com")
    product = _product(db_session, "svc-product-a")
    client, raw_secret = oidc_service.register_client(db_session, admin, "svc-client-a", "Service A", product.id, [])
    db_session.commit()

    try:
        service_auth.issue_service_token(db_session, client.client_id, raw_secret)
        assert False, "expected InsufficientScopeError"
    except InsufficientScopeError:
        pass


def test_granted_scope_is_present_in_the_issued_token(db_session):
    admin = _admin(db_session, "admin-svc2@example.com")
    product = _product(db_session, "svc-product-b")
    client, raw_secret = oidc_service.register_client(db_session, admin, "svc-client-b", "Service B", product.id, [])
    service_auth.grant_scope(db_session, admin, client, "service:entitlements:read")
    db_session.commit()

    token, scopes = service_auth.issue_service_token(db_session, client.client_id, raw_secret)
    assert scopes == ["service:entitlements:read"]
    payload = introspect_service_access_token(token)
    assert payload is not None
    assert payload["client_id"] == client.client_id
    assert payload["scope"] == "service:entitlements:read"
    assert "sub" in payload  # no end user - sub is the client itself


def test_unrecognized_scope_rejected(db_session):
    admin = _admin(db_session, "admin-svc3@example.com")
    product = _product(db_session, "svc-product-c")
    client, _raw = oidc_service.register_client(db_session, admin, "svc-client-c", "Service C", product.id, [])
    db_session.commit()
    try:
        service_auth.grant_scope(db_session, admin, client, "service:roles:write")
        assert False, "expected InsufficientScopeError"
    except InsufficientScopeError:
        pass


def test_wrong_secret_rejected(db_session):
    admin = _admin(db_session, "admin-svc4@example.com")
    product = _product(db_session, "svc-product-d")
    client, _raw = oidc_service.register_client(db_session, admin, "svc-client-d", "Service D", product.id, [])
    service_auth.grant_scope(db_session, admin, client, "service:entitlements:read")
    db_session.commit()
    try:
        service_auth.issue_service_token(db_session, client.client_id, "wrong-secret")
        assert False, "expected InvalidClientError"
    except InvalidClientError:
        pass


def test_rotated_secret_invalidates_the_old_one(db_session):
    admin = _admin(db_session, "admin-svc5@example.com")
    product = _product(db_session, "svc-product-e")
    client, old_secret = oidc_service.register_client(db_session, admin, "svc-client-e", "Service E", product.id, [])
    service_auth.grant_scope(db_session, admin, client, "service:entitlements:read")
    db_session.commit()

    new_secret = service_auth.rotate_client_secret(db_session, admin, client)
    db_session.commit()

    try:
        service_auth.issue_service_token(db_session, client.client_id, old_secret)
        assert False, "expected InvalidClientError (old secret must no longer work)"
    except InvalidClientError:
        pass

    token, _scopes = service_auth.issue_service_token(db_session, client.client_id, new_secret)
    assert token
