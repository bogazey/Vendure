"""Mission 17 (explicitly required, verbatim): "A Gamey support
administrator must not automatically gain administrative access to
Loady. Test this explicitly." `support`/`finance` were seeded roles that
enforced nothing before this mission (see
`docs/platform/RBAC_MATRIX.md`) - this is the real automated test matrix
proving both roles are now wired in, read-only, and exactly as product-
isolated as the existing `admin` role already is
(`test_product_scoped_rbac.py`)."""
from __future__ import annotations

from app.database.models import PaymentRecord, Product, Subscription, User
from app.models.enums import GLOBAL_SCOPE, RoleSlug, product_scope
from app.services import rbac_service

LOADY = "sf-loady"
GAMEY = "sf-gamey"


def _signup(client, email: str) -> None:
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 201, r.text


def _make_scoped(client, db_session, email: str, role: RoleSlug, scope: str) -> User:
    _signup(client, email)
    user = db_session.query(User).filter_by(email=email).first()
    rbac_service.assign_role(db_session, user, role, scope, granted_by=None)
    db_session.commit()
    return user


def _make_super_admin(client, db_session, email: str) -> User:
    return _make_scoped(client, db_session, email, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE)


def _setup_two_products(db_session):
    for pid in (LOADY, GAMEY):
        if db_session.get(Product, pid) is None:
            db_session.add(Product(id=pid, name=pid, domain=f"{pid}.example", status="live"))
    db_session.flush()
    db_session.commit()


def _seed_subscription(db_session, product_id: str, suffix: str) -> Subscription:
    user = User(email=f"subuser-{suffix}@example.com", password_hash="x", email_verified=True)
    db_session.add(user)
    db_session.flush()
    sub = Subscription(
        user_id=user.id, product_id=product_id, provider="paddle",
        provider_customer_ref=f"cust-{suffix}", provider_subscription_ref=f"sub-{suffix}", status="active",
    )
    db_session.add(sub)
    db_session.commit()
    return sub


def _seed_payment(db_session, product_id: str, suffix: str) -> PaymentRecord:
    user = User(email=f"payuser-{suffix}@example.com", password_hash="x", email_verified=True)
    db_session.add(user)
    db_session.flush()
    pay = PaymentRecord(
        user_id=user.id, product_id=product_id, provider="paddle", provider_reference=f"txn-{suffix}",
        amount_cents=999, currency="usd", status="completed",
    )
    db_session.add(pay)
    db_session.commit()
    return pay


# --- support role: /subscriptions --------------------------------------------

def test_product_scoped_support_can_list_own_products_subscriptions(client, db_session):
    _setup_two_products(db_session)
    _seed_subscription(db_session, LOADY, "a")
    _make_scoped(client, db_session, "sf-loady-support1@example.com", RoleSlug.SUPPORT, product_scope(LOADY))

    resp = client.get("/api/v1/admin/subscriptions")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["product_id"] == LOADY


def test_gamey_support_cannot_see_loadys_subscriptions(client, db_session):
    """The mission's exact bounded requirement: a Gamey support account
    must never see Loady's rows, even in a listing endpoint with no
    product_id path parameter to gate at the dependency layer."""
    _setup_two_products(db_session)
    _seed_subscription(db_session, LOADY, "b")
    _seed_subscription(db_session, GAMEY, "c")
    _make_scoped(client, db_session, "sf-gamey-support1@example.com", RoleSlug.SUPPORT, product_scope(GAMEY))

    resp = client.get("/api/v1/admin/subscriptions")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["product_id"] == GAMEY
    assert all(r["product_id"] != LOADY for r in rows)


def test_gamey_support_gains_no_administrative_access_to_loady_at_all(client, db_session):
    """The mission's exact wording, tested against every admin surface a
    "Gamey support" account could conceivably try: Loady's plans, Loady's
    product detail/update/verify, and global-admin-only routes. Every one
    of these must reject - `support` grants read access to subscriptions
    only, never anything else, never another product's anything."""
    _setup_two_products(db_session)
    _make_scoped(client, db_session, "sf-gamey-support2@example.com", RoleSlug.SUPPORT, product_scope(GAMEY))

    assert client.get(f"/api/v1/admin/products/{LOADY}").status_code == 403
    assert client.get(f"/api/v1/admin/products/{LOADY}/plans").status_code == 403
    assert client.patch(f"/api/v1/admin/products/{LOADY}", json={"name": "Hijacked"}).status_code == 403
    assert client.get(f"/api/v1/admin/products/{LOADY}/verify").status_code == 403
    assert client.post(f"/api/v1/admin/products/{LOADY}/active", json={"is_active": False}).status_code == 403
    assert client.get("/api/v1/admin/users").status_code == 403
    assert client.get("/api/v1/admin/overview").status_code == 403
    assert client.get("/api/v1/admin/payments").status_code == 403  # support, not finance
    assert client.get("/api/v1/admin/revenue/metrics", params={"product_id": GAMEY}).status_code == 403


def test_gamey_support_also_gains_no_access_to_gameys_own_admin_surfaces(client, db_session):
    """`support` is deliberately narrower than `admin` even for the
    SAME product - it must not inherit any admin capability just because
    it's scoped to the product it's allowed to see subscriptions for."""
    _setup_two_products(db_session)
    _make_scoped(client, db_session, "sf-gamey-support3@example.com", RoleSlug.SUPPORT, product_scope(GAMEY))

    assert client.get(f"/api/v1/admin/products/{GAMEY}").status_code == 403
    assert client.get(f"/api/v1/admin/products/{GAMEY}/plans").status_code == 403
    assert client.patch(f"/api/v1/admin/products/{GAMEY}", json={"name": "Hijacked"}).status_code == 403
    assert client.post(f"/api/v1/admin/products/{GAMEY}/plans", json={"slug": "x", "name": "X"}).status_code == 403


def test_global_support_sees_every_products_subscriptions(client, db_session):
    """A global-scoped support role is unrestricted, exactly like global
    admin - checked as a subset (not equality) since the shared test
    database accumulates other test files' rows across the whole
    session; the point is LOADY's and GAMEY's rows are both visible, not
    that these two are the only rows that will ever exist."""
    _setup_two_products(db_session)
    _seed_subscription(db_session, LOADY, "d")
    _seed_subscription(db_session, GAMEY, "e")
    _make_scoped(client, db_session, "sf-global-support1@example.com", RoleSlug.SUPPORT, GLOBAL_SCOPE)

    resp = client.get("/api/v1/admin/subscriptions", params={"limit": 500})
    assert resp.status_code == 200
    product_ids = {r["product_id"] for r in resp.json()}
    assert {LOADY, GAMEY} <= product_ids


def test_plain_user_still_rejected_from_subscriptions(client, db_session):
    _setup_two_products(db_session)
    _signup(client, "sf-plain1@example.com")
    resp = client.get("/api/v1/admin/subscriptions")
    assert resp.status_code == 403


def test_support_role_cannot_mutate_anything_it_can_read(client, db_session):
    """Deliberately minimal, read-only (mission requirement) - there is
    no POST/PATCH/DELETE variant of `/subscriptions` today, so this
    confirms `support` cannot reach any of the mutation routes that
    happen to share the same product scope."""
    _setup_two_products(db_session)
    _make_scoped(client, db_session, "sf-gamey-support4@example.com", RoleSlug.SUPPORT, product_scope(GAMEY))

    assert client.post(f"/api/v1/admin/products/{GAMEY}/plans", json={"slug": "y", "name": "Y"}).status_code == 403


# --- finance role: /payments, /revenue/metrics -------------------------------

def test_product_scoped_finance_can_list_own_products_payments(client, db_session):
    _setup_two_products(db_session)
    _seed_payment(db_session, LOADY, "f")
    _make_scoped(client, db_session, "sf-loady-finance1@example.com", RoleSlug.FINANCE, product_scope(LOADY))

    resp = client.get("/api/v1/admin/payments")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["product_id"] == LOADY


def test_gamey_finance_cannot_see_loadys_payments(client, db_session):
    _setup_two_products(db_session)
    _seed_payment(db_session, LOADY, "g")
    _seed_payment(db_session, GAMEY, "h")
    _make_scoped(client, db_session, "sf-gamey-finance1@example.com", RoleSlug.FINANCE, product_scope(GAMEY))

    resp = client.get("/api/v1/admin/payments")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["product_id"] == GAMEY
    assert all(r["product_id"] != LOADY for r in rows)


def test_gamey_finance_can_read_gameys_own_revenue_metrics(client, db_session):
    _setup_two_products(db_session)
    _seed_payment(db_session, GAMEY, "i")
    _make_scoped(client, db_session, "sf-gamey-finance2@example.com", RoleSlug.FINANCE, product_scope(GAMEY))

    resp = client.get("/api/v1/admin/revenue/metrics", params={"product_id": GAMEY})
    assert resp.status_code == 200, resp.text


def test_gamey_finance_cannot_read_loadys_revenue_metrics(client, db_session):
    _setup_two_products(db_session)
    _make_scoped(client, db_session, "sf-gamey-finance3@example.com", RoleSlug.FINANCE, product_scope(GAMEY))

    resp = client.get("/api/v1/admin/revenue/metrics", params={"product_id": LOADY})
    assert resp.status_code == 403


def test_product_scoped_finance_cannot_read_ecosystem_wide_metrics(client, db_session):
    """No product_id at all means "every product's revenue" - a product-
    scoped finance role must not be able to see that, exactly like a
    product-scoped admin already can't (mission-brief Phase 12)."""
    _setup_two_products(db_session)
    _make_scoped(client, db_session, "sf-gamey-finance4@example.com", RoleSlug.FINANCE, product_scope(GAMEY))

    resp = client.get("/api/v1/admin/revenue/metrics")
    assert resp.status_code == 403


def test_global_finance_can_read_ecosystem_wide_metrics(client, db_session):
    _setup_two_products(db_session)
    _make_scoped(client, db_session, "sf-global-finance1@example.com", RoleSlug.FINANCE, GLOBAL_SCOPE)

    resp = client.get("/api/v1/admin/revenue/metrics")
    assert resp.status_code == 200, resp.text


def test_gamey_finance_gains_no_administrative_access_to_loady_at_all(client, db_session):
    _setup_two_products(db_session)
    _make_scoped(client, db_session, "sf-gamey-finance5@example.com", RoleSlug.FINANCE, product_scope(GAMEY))

    assert client.get(f"/api/v1/admin/products/{LOADY}").status_code == 403
    assert client.patch(f"/api/v1/admin/products/{LOADY}", json={"name": "Hijacked"}).status_code == 403
    assert client.get("/api/v1/admin/subscriptions").status_code == 403  # finance, not support
    assert client.get("/api/v1/admin/users").status_code == 403


def test_finance_role_cannot_mutate_anything(client, db_session):
    _setup_two_products(db_session)
    _make_scoped(client, db_session, "sf-gamey-finance6@example.com", RoleSlug.FINANCE, product_scope(GAMEY))

    assert client.post(f"/api/v1/admin/products/{GAMEY}/plans", json={"slug": "z", "name": "Z"}).status_code == 403
    assert client.post(f"/api/v1/admin/clients/{GAMEY}-does-not-exist/active", json={"is_active": False}).status_code in (403, 404)


def test_admin_role_still_works_unaffected_by_the_new_roles(client, db_session):
    """Regression guard: adding support/finance enforcement must not
    have narrowed what a plain product-scoped `admin` could already do."""
    _setup_two_products(db_session)
    _seed_subscription(db_session, LOADY, "j")
    _seed_payment(db_session, LOADY, "k")
    _make_scoped(client, db_session, "sf-loady-admin1@example.com", RoleSlug.ADMIN, product_scope(LOADY))

    assert client.get("/api/v1/admin/subscriptions").status_code == 200
    assert client.get("/api/v1/admin/payments").status_code == 200
    assert client.get("/api/v1/admin/revenue/metrics", params={"product_id": LOADY}).status_code == 200
    assert client.get(f"/api/v1/admin/products/{LOADY}").status_code == 200


def test_super_admin_still_sees_everything_unaffected(client, db_session):
    _setup_two_products(db_session)
    _seed_subscription(db_session, LOADY, "l")
    _seed_subscription(db_session, GAMEY, "m")
    _seed_payment(db_session, LOADY, "n")
    _seed_payment(db_session, GAMEY, "o")
    _make_super_admin(client, db_session, "sf-super1@example.com")

    subs = client.get("/api/v1/admin/subscriptions", params={"limit": 500}).json()
    pays = client.get("/api/v1/admin/payments", params={"limit": 500}).json()
    assert {LOADY, GAMEY} <= {s["product_id"] for s in subs}
    assert {LOADY, GAMEY} <= {p["product_id"] for p in pays}
    assert client.get("/api/v1/admin/revenue/metrics").status_code == 200
