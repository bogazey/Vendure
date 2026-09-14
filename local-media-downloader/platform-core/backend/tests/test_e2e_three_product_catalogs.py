"""Mission 6 continuation - MANDATORY E2E CATALOG TEST.

Creates three products, styled after Loady/Gamey/Filey, entirely through
the real administration HTTP API (not direct service calls) - proving a
new product's catalog can be built without touching Platform Core
source. Each product gets intentionally different plan names, plan
counts, and capabilities. Proves: catalog isolation, price isolation,
entitlement isolation, admin scope isolation, version preservation,
historical price preservation, upgrade behavior, downgrade behavior,
gifted eligibility, and provider mapping.
"""
from __future__ import annotations

from app.database.models import Product, User
from app.models.enums import GLOBAL_SCOPE, RoleSlug
from app.services import rbac_service
from app.services.rate_limit_service import admin_mutation_limiter


def _signup(client, email: str) -> User:
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 201, r.text


def _make_super_admin(client, db_session, email: str) -> None:
    _signup(client, email)
    user = db_session.query(User).filter_by(email=email).first()
    rbac_service.assign_role(db_session, user, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE, granted_by=None)
    db_session.commit()


def _register_product(client, product_id: str, name: str) -> None:
    admin_mutation_limiter.clear()
    r = client.post("/api/v1/admin/products", json={
        "id": product_id, "name": name, "domain": f"{product_id}.example", "status": "live", "icon_ref": None,
    })
    assert r.status_code == 200, r.text


def _create_plan(client, product_id: str, slug: str, name: str, **extra) -> dict:
    admin_mutation_limiter.clear()
    r = client.post(f"/api/v1/admin/catalog/products/{product_id}/plans", json={"slug": slug, "name": name, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _define_capability(client, product_id: str, key: str, value_type: str, **extra) -> None:
    admin_mutation_limiter.clear()
    r = client.post(f"/api/v1/admin/products/{product_id}/capabilities", json={"key": key, "value_type": value_type, **extra})
    assert r.status_code == 200, r.text


def _set_capability(client, plan_id: str, key: str, value) -> None:
    admin_mutation_limiter.clear()
    r = client.put(f"/api/v1/admin/plans/{plan_id}/capabilities/{key}", json={"value": value})
    assert r.status_code == 200, r.text


def _publish_version(client, plan_id: str) -> dict:
    admin_mutation_limiter.clear()
    r = client.post(f"/api/v1/admin/catalog/plans/{plan_id}/versions")
    assert r.status_code == 200, r.text
    return r.json()


def _create_price(client, plan_id: str, **body) -> dict:
    admin_mutation_limiter.clear()
    r = client.post(f"/api/v1/admin/catalog/plans/{plan_id}/prices", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_three_independent_product_catalogs_via_real_admin_api(client, db_session):
    _make_super_admin(client, db_session, "e2e-super@example.com")

    # === LOADY-STYLE ===
    _register_product(client, "e2e-loady", "E2E Loady")
    loady_free = _create_plan(client, "e2e-loady", "free", "Free", upgrade_rank=0)
    loady_pro = _create_plan(client, "e2e-loady", "pro", "Pro", upgrade_rank=1)
    loady_creator = _create_plan(client, "e2e-loady", "creator", "Creator", upgrade_rank=2)

    for key, vtype in [
        ("max_resolution", "integer"), ("daily_download_limit", "integer"),
        ("concurrent_jobs", "integer"), ("ads_enabled", "boolean"),
    ]:
        _define_capability(client, "e2e-loady", key, vtype)

    _set_capability(client, loady_free["id"], "max_resolution", 480)
    _set_capability(client, loady_free["id"], "daily_download_limit", 5)
    _set_capability(client, loady_free["id"], "concurrent_jobs", 1)
    _set_capability(client, loady_free["id"], "ads_enabled", True)

    _set_capability(client, loady_pro["id"], "max_resolution", 1080)
    _set_capability(client, loady_pro["id"], "daily_download_limit", 50)
    _set_capability(client, loady_pro["id"], "concurrent_jobs", 3)
    _set_capability(client, loady_pro["id"], "ads_enabled", False)

    _set_capability(client, loady_creator["id"], "max_resolution", -1)  # unlimited
    _set_capability(client, loady_creator["id"], "daily_download_limit", -1)
    _set_capability(client, loady_creator["id"], "concurrent_jobs", 10)
    _set_capability(client, loady_creator["id"], "ads_enabled", False)

    for plan in (loady_free, loady_pro, loady_creator):
        _publish_version(client, plan["id"])

    loady_pro_price = _create_price(client, loady_pro["id"], provider="paddle", currency="usd", amount_cents=499, interval="month", provider_price_id="pri_loady_pro_m")
    _create_price(client, loady_pro["id"], provider="paddle", currency="usd", amount_cents=4999, interval="year", provider_price_id="pri_loady_pro_y")

    # === GAMEY-STYLE (intentionally different shape) ===
    _register_product(client, "e2e-gamey", "E2E Gamey")
    gamey_free = _create_plan(client, "e2e-gamey", "free", "Free", upgrade_rank=0)
    gamey_plus = _create_plan(client, "e2e-gamey", "gamer-plus", "Gamer+", upgrade_rank=1)
    gamey_elite = _create_plan(client, "e2e-gamey", "elite", "Elite", upgrade_rank=2, gifted_eligible=False)

    for key, vtype in [
        ("purchase_discount_percent", "integer"), ("monthly_bonus", "integer"),
        ("priority_support", "boolean"), ("purchase_limit", "integer"),
    ]:
        _define_capability(client, "e2e-gamey", key, vtype)

    _set_capability(client, gamey_free["id"], "purchase_discount_percent", 0)
    _set_capability(client, gamey_free["id"], "monthly_bonus", 0)
    _set_capability(client, gamey_free["id"], "priority_support", False)
    _set_capability(client, gamey_free["id"], "purchase_limit", 3)

    _set_capability(client, gamey_plus["id"], "purchase_discount_percent", 10)
    _set_capability(client, gamey_plus["id"], "monthly_bonus", 500)
    _set_capability(client, gamey_plus["id"], "priority_support", True)
    _set_capability(client, gamey_plus["id"], "purchase_limit", 20)

    _set_capability(client, gamey_elite["id"], "purchase_discount_percent", 25)
    _set_capability(client, gamey_elite["id"], "monthly_bonus", 2000)
    _set_capability(client, gamey_elite["id"], "priority_support", True)
    _set_capability(client, gamey_elite["id"], "purchase_limit", -1)

    for plan in (gamey_free, gamey_plus, gamey_elite):
        _publish_version(client, plan["id"])

    _create_price(client, gamey_plus["id"], provider="paddle", currency="usd", amount_cents=999, interval="month", provider_price_id="pri_gamey_plus_m")

    # === FILEY-STYLE ===
    _register_product(client, "e2e-filey", "E2E Filey")
    filey_free = _create_plan(client, "e2e-filey", "free", "Free", upgrade_rank=0)
    filey_personal = _create_plan(client, "e2e-filey", "personal", "Personal", upgrade_rank=1)
    filey_business = _create_plan(client, "e2e-filey", "business", "Business", upgrade_rank=2)

    for key, vtype in [
        ("max_file_size_mb", "integer"), ("daily_conversions", "integer"),
        ("batch_conversion", "boolean"), ("storage_days", "integer"),
    ]:
        _define_capability(client, "e2e-filey", key, vtype)

    _set_capability(client, filey_free["id"], "max_file_size_mb", 25)
    _set_capability(client, filey_free["id"], "daily_conversions", 10)
    _set_capability(client, filey_free["id"], "batch_conversion", False)
    _set_capability(client, filey_free["id"], "storage_days", 1)

    _set_capability(client, filey_personal["id"], "max_file_size_mb", 500)
    _set_capability(client, filey_personal["id"], "daily_conversions", 200)
    _set_capability(client, filey_personal["id"], "batch_conversion", True)
    _set_capability(client, filey_personal["id"], "storage_days", 30)

    _set_capability(client, filey_business["id"], "max_file_size_mb", -1)
    _set_capability(client, filey_business["id"], "daily_conversions", -1)
    _set_capability(client, filey_business["id"], "batch_conversion", True)
    _set_capability(client, filey_business["id"], "storage_days", 365)

    for plan in (filey_free, filey_personal, filey_business):
        _publish_version(client, plan["id"])

    filey_business_price = _create_price(client, filey_business["id"], provider="paddle", currency="eur", amount_cents=1999, interval="month", provider_price_id="pri_filey_biz_m")

    # ================================================================
    # PROOF 1: catalog isolation - different plan names/counts/capabilities
    # ================================================================
    loady_plans = client.get("/api/v1/admin/catalog/products/e2e-loady/plans").json()
    gamey_plans = client.get("/api/v1/admin/catalog/products/e2e-gamey/plans").json()
    filey_plans = client.get("/api/v1/admin/catalog/products/e2e-filey/plans").json()
    assert {p["slug"] for p in loady_plans} == {"free", "pro", "creator"}
    assert {p["slug"] for p in gamey_plans} == {"free", "gamer-plus", "elite"}
    assert {p["slug"] for p in filey_plans} == {"free", "personal", "business"}

    loady_caps = {c["key"] for c in client.get("/api/v1/admin/products/e2e-loady/capabilities").json()}
    gamey_caps = {c["key"] for c in client.get("/api/v1/admin/products/e2e-gamey/capabilities").json()}
    filey_caps = {c["key"] for c in client.get("/api/v1/admin/products/e2e-filey/capabilities").json()}
    assert loady_caps.isdisjoint(gamey_caps)
    assert loady_caps.isdisjoint(filey_caps)
    assert gamey_caps.isdisjoint(filey_caps)

    # ================================================================
    # PROOF 2: price isolation + provider mapping
    # ================================================================
    loady_pro_prices = client.get(f"/api/v1/admin/catalog/plans/{loady_pro['id']}/prices").json()
    assert len(loady_pro_prices) == 2  # monthly + annual
    assert {p["provider_price_id"] for p in loady_pro_prices} == {"pri_loady_pro_m", "pri_loady_pro_y"}
    assert filey_business_price["currency"] == "EUR"
    assert loady_pro_price["currency"] == "USD"

    # ================================================================
    # PROOF 3: entitlement isolation - granting Loady Pro must not touch Gamey/Filey
    # ================================================================
    # Inserted directly via the ORM, never through the shared `client`'s
    # own /signup endpoint - that would overwrite the super-admin's
    # session cookie already sitting in the same TestClient's cookie jar
    # with the new target's session (see test_admin.py's own precedent).
    from app.security.passwords import hash_password

    target = User(email="e2e-target@example.com", password_hash=hash_password("correct-horse-battery"), email_verified=True)
    db_session.add(target)
    db_session.commit()
    target_id = target.id

    grant = client.patch(f"/api/v1/admin/users/{target_id}/entitlements", json={
        "product_id": "e2e-loady", "plan_slug": "pro", "source": "paddle", "expires_at": None, "reason": "e2e",
    })
    assert grant.status_code == 200, grant.text

    loady_ee = client.get(f"/api/v1/admin/users/{target_id}/effective-entitlements", params={"product_id": "e2e-loady"}).json()
    gamey_ee = client.get(f"/api/v1/admin/users/{target_id}/effective-entitlements", params={"product_id": "e2e-gamey"}).json()
    filey_ee = client.get(f"/api/v1/admin/users/{target_id}/effective-entitlements", params={"product_id": "e2e-filey"}).json()

    assert loady_ee["capabilities"]["max_resolution"] == 1080
    assert loady_ee["capabilities"]["ads_enabled"] is False
    assert gamey_ee["capabilities"] == {}  # no Loady entitlement leaks into Gamey
    assert filey_ee["capabilities"] == {}

    # ================================================================
    # PROOF 4: upgrade behavior - Loady Pro -> Creator via re-grant
    # ================================================================
    upgrade = client.patch(f"/api/v1/admin/users/{target_id}/entitlements", json={
        "product_id": "e2e-loady", "plan_slug": "creator", "source": "paddle", "expires_at": None, "reason": "upgrade",
    })
    assert upgrade.status_code == 200
    loady_ee_after_upgrade = client.get(f"/api/v1/admin/users/{target_id}/effective-entitlements", params={"product_id": "e2e-loady"}).json()
    assert loady_ee_after_upgrade["capabilities"]["max_resolution"] == -1  # unlimited, Creator's value

    # ================================================================
    # PROOF 5: downgrade behavior - Creator -> Free (still source=paddle:
    # a downgrade within an existing paid relationship, not a takeover by
    # a gifted/internal source - the paid-precedence guard correctly
    # rejects switching source away from paddle here, exactly as
    # ENTITLEMENTS.md/GRAND_ADMIN.md document)
    # ================================================================
    downgrade = client.patch(f"/api/v1/admin/users/{target_id}/entitlements", json={
        "product_id": "e2e-loady", "plan_slug": "free", "source": "paddle", "expires_at": None, "reason": "downgrade",
    })
    assert downgrade.status_code == 200, downgrade.text
    loady_ee_after_downgrade = client.get(f"/api/v1/admin/users/{target_id}/effective-entitlements", params={"product_id": "e2e-loady"}).json()
    assert loady_ee_after_downgrade["capabilities"]["max_resolution"] == 480

    # ================================================================
    # PROOF 6: gifted eligibility - Gamey Elite is gift-ineligible by design
    # ================================================================
    ineligible_gift = client.post(f"/api/v1/admin/users/{target_id}/gifts", json={
        "product_id": "e2e-gamey", "plan_slug": "elite", "reason": "should fail",
    })
    assert ineligible_gift.status_code == 403

    eligible_gift = client.post(f"/api/v1/admin/users/{target_id}/gifts", json={
        "product_id": "e2e-gamey", "plan_slug": "gamer-plus", "reason": "should succeed",
    })
    assert eligible_gift.status_code == 200, eligible_gift.text

    # ================================================================
    # PROOF 7: version preservation - editing Loady free's capabilities
    # after granting must not retroactively change the existing grant
    # ================================================================
    early_user = User(email="e2e-early@example.com", password_hash=hash_password("correct-horse-battery"), email_verified=True)
    db_session.add(early_user)
    db_session.commit()
    early_user_id = early_user.id
    client.patch(f"/api/v1/admin/users/{early_user_id}/entitlements", json={
        "product_id": "e2e-loady", "plan_slug": "free", "source": "internal", "expires_at": None, "reason": "early",
    })
    early_before = client.get(f"/api/v1/admin/users/{early_user_id}/effective-entitlements", params={"product_id": "e2e-loady"}).json()
    assert early_before["capabilities"]["daily_download_limit"] == 5

    _set_capability(client, loady_free["id"], "daily_download_limit", 2)  # catalog tightens the free tier
    _publish_version(client, loady_free["id"])

    early_after = client.get(f"/api/v1/admin/users/{early_user_id}/effective-entitlements", params={"product_id": "e2e-loady"}).json()
    assert early_after["capabilities"]["daily_download_limit"] == 5  # frozen - unaffected by the catalog change

    # ================================================================
    # PROOF 8: historical price preservation - retiring loady_pro_price
    # must not change what's already been sold at that price
    # ================================================================
    retire = client.post(f"/api/v1/admin/catalog/prices/{loady_pro_price['id']}/retire", json={"reason": "price increase"})
    assert retire.status_code == 200
    new_price = _create_price(client, loady_pro["id"], provider="paddle", currency="usd", amount_cents=599, interval="month", provider_price_id="pri_loady_pro_m_v2")
    old_price_after = client.get(f"/api/v1/admin/catalog/plans/{loady_pro['id']}/prices").json()
    still_there = next(p for p in old_price_after if p["id"] == loady_pro_price["id"])
    assert still_there["amount_cents"] == 499  # never mutated
    assert still_there["is_active"] is False
    assert new_price["amount_cents"] == 599

    # ================================================================
    # PROOF 9: admin scope isolation - a Loady-only admin cannot touch Gamey/Filey
    # ================================================================
    from app.models.enums import product_scope

    scoped_signup = client.post("/api/v1/auth/signup", json={"email": "e2e-loady-admin@example.com", "password": "correct-horse-battery"})
    scoped_admin_id = scoped_signup.json()["id"]
    scoped_admin = db_session.get(User, scoped_admin_id)
    rbac_service.assign_role(db_session, scoped_admin, RoleSlug.ADMIN, product_scope("e2e-loady"), granted_by=None)
    db_session.commit()

    # NOTE: this session's cookie jar is currently the super-admin's, not
    # the scoped admin's - log in as the scoped admin explicitly.
    client.post("/api/v1/auth/login", json={"email": "e2e-loady-admin@example.com", "password": "correct-horse-battery"})

    own_product_ok = client.get("/api/v1/admin/catalog/products/e2e-loady/plans")
    assert own_product_ok.status_code == 200
    other_product_denied = client.get("/api/v1/admin/catalog/products/e2e-gamey/plans")
    assert other_product_denied.status_code == 403
    third_product_denied = client.get("/api/v1/admin/catalog/products/e2e-filey/plans")
    assert third_product_denied.status_code == 403
