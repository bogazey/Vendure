"""Mission 6 continuation: Grand Admin product onboarding UI's backend -
`POST /api/v1/admin/products/onboard` (create a product + its initial
OAuth client in one super_admin-gated action, secret shown exactly once)
and `POST /api/v1/admin/clients/{id}/rotate-secret`. Adversarial tests
proving super_admin-only authorization, atomicity on failure, and that a
plaintext secret is never retrievable after the one response that
generated it."""
from __future__ import annotations

from app.database.models import AuditLog, OAuthClient, Product, User
from app.models.enums import GLOBAL_SCOPE, AuditAction, RoleSlug, product_scope
from app.security import passwords
from app.services import rbac_service


def _signup(client, email: str) -> None:
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 201


def _make_super_admin(client, db_session, email: str) -> User:
    _signup(client, email)
    user = db_session.query(User).filter_by(email=email).first()
    rbac_service.assign_role(db_session, user, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE, granted_by=None)
    db_session.commit()
    return user


def _make_global_admin(client, db_session, email: str) -> User:
    _signup(client, email)
    user = db_session.query(User).filter_by(email=email).first()
    rbac_service.assign_role(db_session, user, RoleSlug.ADMIN, GLOBAL_SCOPE, granted_by=None)
    db_session.commit()
    return user


def _make_product_admin(client, db_session, email: str, product_id: str) -> User:
    _signup(client, email)
    user = db_session.query(User).filter_by(email=email).first()
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.commit()
    rbac_service.assign_role(db_session, user, RoleSlug.ADMIN, product_scope(product_id), granted_by=None)
    db_session.commit()
    return user


def _onboard_payload(suffix: str) -> dict:
    return {
        "id": f"onboard-{suffix}",
        "name": f"Onboard {suffix}",
        "domain": f"onboard-{suffix}.example",
        "description": "A brand new ecosystem product.",
        "is_discoverable": True,
        "status": "planned",
        "client_id": f"onboard-{suffix}-client",
        "client_name": f"Onboard {suffix} Client",
        "redirect_uris": [f"https://onboard-{suffix}.example/auth/callback"],
    }


def test_super_admin_can_onboard_a_new_product_and_secret_is_shown_exactly_once(client, db_session):
    _make_super_admin(client, db_session, "onboard-super1@example.com")
    payload = _onboard_payload("a")

    resp = client.post("/api/v1/admin/products/onboard", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["product"]["id"] == "onboard-a"
    assert body["product"]["description"] == "A brand new ecosystem product."
    assert body["product"]["is_discoverable"] is True
    assert body["client_id"] == "onboard-a-client"
    assert isinstance(body["client_secret"], str) and len(body["client_secret"]) > 10

    # The stored client only ever has a hash - never the plaintext.
    stored = db_session.get(OAuthClient, "onboard-a-client")
    assert stored is not None
    assert stored.client_secret_hash != body["client_secret"]
    assert passwords.verify_password(body["client_secret"], stored.client_secret_hash)


def test_onboarding_response_is_the_only_place_the_secret_ever_appears(client, db_session):
    _make_super_admin(client, db_session, "onboard-super2@example.com")
    resp = client.post("/api/v1/admin/products/onboard", json=_onboard_payload("b"))
    secret = resp.json()["client_secret"]

    listing = client.get("/api/v1/admin/clients")
    assert listing.status_code == 200
    assert secret not in listing.text
    for row in listing.json():
        assert "client_secret" not in row
        assert "client_secret_hash" not in row


def test_duplicate_product_id_is_rejected(client, db_session):
    _make_super_admin(client, db_session, "onboard-super3@example.com")
    payload = _onboard_payload("c")
    assert client.post("/api/v1/admin/products/onboard", json=payload).status_code == 200

    payload2 = dict(payload)
    payload2["client_id"] = "onboard-c-client-2"
    resp = client.post("/api/v1/admin/products/onboard", json=payload2)
    assert resp.status_code in (400, 409, 422)


def test_duplicate_client_id_rolls_back_the_product_too(client, db_session):
    """Atomicity: if the client half of onboarding fails, the product half
    must not be left behind as an orphaned, client-less product."""
    _make_super_admin(client, db_session, "onboard-super4@example.com")
    # Pre-register a client under the id the onboarding payload will reuse.
    payload = _onboard_payload("d")
    from app.services import oidc_service
    admin_row = db_session.query(User).filter_by(email="onboard-super4@example.com").first()
    oidc_service.register_client(db_session, admin_row, payload["client_id"], "Pre-existing", None, ["https://pre.example/cb"])
    db_session.commit()

    resp = client.post("/api/v1/admin/products/onboard", json=payload)
    assert resp.status_code in (400, 409, 422)
    assert db_session.get(Product, payload["id"]) is None


def test_global_admin_without_super_admin_cannot_onboard_a_product(client, db_session):
    _make_global_admin(client, db_session, "onboard-globaladmin1@example.com")
    resp = client.post("/api/v1/admin/products/onboard", json=_onboard_payload("e"))
    assert resp.status_code == 403


def test_product_scoped_admin_cannot_onboard_a_new_global_product(client, db_session):
    _make_product_admin(client, db_session, "onboard-scoped1@example.com", "onboard-existing-product")
    resp = client.post("/api/v1/admin/products/onboard", json=_onboard_payload("f"))
    assert resp.status_code == 403


def test_plain_user_cannot_onboard_a_product(client, db_session):
    _signup(client, "onboard-plain1@example.com")
    resp = client.post("/api/v1/admin/products/onboard", json=_onboard_payload("g"))
    assert resp.status_code == 403


def test_onboarding_records_audit_events_for_both_product_and_client(client, db_session):
    admin = _make_super_admin(client, db_session, "onboard-super5@example.com")
    resp = client.post("/api/v1/admin/products/onboard", json=_onboard_payload("h"))
    assert resp.status_code == 200

    entries = db_session.query(AuditLog).filter_by(actor_user_id=admin.id).all()
    actions = {e.action for e in entries}
    assert AuditAction.PRODUCT_CREATED.value in actions
    assert AuditAction.CLIENT_REGISTERED.value in actions
    product_entry = next(e for e in entries if e.action == AuditAction.PRODUCT_CREATED.value and e.target_id == "onboard-h")
    assert product_entry.product_id == "onboard-h"
    client_entry = next(e for e in entries if e.action == AuditAction.CLIENT_REGISTERED.value and e.target_id == "onboard-h-client")
    assert client_entry.product_id == "onboard-h"


# --- Secret rotation ---------------------------------------------------------------


def test_super_admin_can_rotate_a_client_secret_and_the_old_one_stops_verifying(client, db_session):
    _make_super_admin(client, db_session, "onboard-super6@example.com")
    onboard_resp = client.post("/api/v1/admin/products/onboard", json=_onboard_payload("i"))
    old_secret = onboard_resp.json()["client_secret"]
    client_id = onboard_resp.json()["client_id"]

    rotate_resp = client.post(f"/api/v1/admin/clients/{client_id}/rotate-secret")
    assert rotate_resp.status_code == 200, rotate_resp.text
    new_secret = rotate_resp.json()["client_secret"]
    assert new_secret != old_secret

    stored = db_session.get(OAuthClient, client_id)
    assert not passwords.verify_password(old_secret, stored.client_secret_hash)
    assert passwords.verify_password(new_secret, stored.client_secret_hash)


def test_rotate_secret_records_an_audit_event(client, db_session):
    admin = _make_super_admin(client, db_session, "onboard-super7@example.com")
    onboard_resp = client.post("/api/v1/admin/products/onboard", json=_onboard_payload("j"))
    client_id = onboard_resp.json()["client_id"]

    rotate_resp = client.post(f"/api/v1/admin/clients/{client_id}/rotate-secret")
    assert rotate_resp.status_code == 200

    entries = db_session.query(AuditLog).filter_by(actor_user_id=admin.id, target_id=client_id).all()
    assert any(e.action == AuditAction.SERVICE_CLIENT_SECRET_ROTATED.value for e in entries)


def test_global_admin_without_super_admin_cannot_rotate_a_secret(client, db_session):
    super_admin = _make_super_admin(client, db_session, "onboard-super8@example.com")
    onboard_resp = client.post("/api/v1/admin/products/onboard", json=_onboard_payload("k"))
    client_id = onboard_resp.json()["client_id"]

    _make_global_admin(client, db_session, "onboard-globaladmin2@example.com")
    resp = client.post(f"/api/v1/admin/clients/{client_id}/rotate-secret")
    assert resp.status_code == 403


def test_product_scoped_admin_cannot_rotate_a_secret_even_for_their_own_product(client, db_session):
    """Secret rotation is `require_super_admin`, unconditionally - unlike
    plan/price/gift management, a product-scoped admin gets no exception
    here even for their own product's client."""
    _make_super_admin(client, db_session, "onboard-super9@example.com")
    onboard_resp = client.post("/api/v1/admin/products/onboard", json=_onboard_payload("l"))
    client_id = onboard_resp.json()["client_id"]
    product_id = onboard_resp.json()["product"]["id"]

    _make_product_admin(client, db_session, "onboard-scoped2@example.com", product_id)
    resp = client.post(f"/api/v1/admin/clients/{client_id}/rotate-secret")
    assert resp.status_code == 403
