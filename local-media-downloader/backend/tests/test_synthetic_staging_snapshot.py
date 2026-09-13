"""Mission 5, phase 4: the synthetic pre-migration dataset generator used for
the local production-migration rehearsal - see
app/scripts/generate_synthetic_staging_snapshot.py and
docs/platform/PRODUCTION_REHEARSAL_PLAN.md. This proves the generator itself
(counts, determinism, reset-cleanliness), not the migration - see
platform-core/backend/tests/test_loady_migration.py for that."""
from __future__ import annotations

import pytest

from app.database.commercial_models import RefreshToken, Subscription, UsageEvent, UsagePeriod, User
from app.scripts.generate_synthetic_staging_snapshot import (
    PERSONAS,
    SYNTHETIC_EMAIL_SUFFIX,
    build_manifest,
    generate,
    reset,
)


@pytest.fixture(autouse=True)
def _clean_synthetic_rows(db_session):
    """The generator writes real, persistent rows against the shared test
    sqlite file (not a per-test transaction) - unlike most of this suite's
    fixtures, so leftover rows from one test would collide with the next
    test's deterministic seed. Reset before AND after every test in this
    file so it never depends on run order and never leaks into other test
    files either."""
    reset(db_session)
    yield
    reset(db_session)


def test_generates_at_least_fifty_users_across_every_persona(db_session):
    records = generate(session=db_session)
    assert len(records) >= 50
    labels = {r["persona"] for r in records}
    assert labels == {p.label for p in PERSONAS}


def test_every_email_carries_the_reserved_synthetic_suffix(db_session):
    records = generate(session=db_session)
    assert all(r["email"].endswith(SYNTHETIC_EMAIL_SUFFIX) for r in records)


def test_generation_is_deterministic_given_the_same_seed(db_session):
    a = generate(seed=4242, session=db_session)
    reset(db_session)
    b = generate(seed=4242, session=db_session)
    a_shape = [{k: v for k, v in r.items() if k != "user_id"} for r in a]
    b_shape = [{k: v for k, v in r.items() if k != "user_id"} for r in b]
    assert a_shape == b_shape


def test_includes_the_required_edge_cases(db_session):
    records = generate(session=db_session)
    already_linked = [r for r in records if r["already_linked"]]
    assert len(already_linked) == 1

    disabled = [r for r in records if r["status"] == "disabled"]
    assert len(disabled) >= 3  # disabled_free(2) + disabled_pro(1) + unverified_disabled_edge(1)

    unverified = [r for r in records if not r["verified"]]
    assert len(unverified) >= 5

    admins = [r for r in records if r["role"] == "admin"]
    assert len(admins) == 2


def test_manifest_checksum_detects_any_later_edit():
    import hashlib
    import json

    records = [{"email": "a@x", "plan": "free", "status": "active", "verified": True, "role": "user", "already_linked": False, "history_rows": 0}]
    manifest = build_manifest(records)

    # The checksum must match a hash recomputed from the manifest's own
    # content right now (proving it's a real content hash, not a placeholder)...
    recomputed_now = hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items() if k != "checksum_sha256"}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    assert manifest["checksum_sha256"] == recomputed_now

    # ...and a single silent post-write edit must break that match, which is
    # the entire point of shipping the checksum alongside the manifest file.
    tampered = dict(manifest)
    tampered["total_users"] = 999
    recomputed_after_edit = hashlib.sha256(
        json.dumps({k: v for k, v in tampered.items() if k != "checksum_sha256"}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    assert recomputed_after_edit != manifest["checksum_sha256"]


def test_reset_removes_exactly_the_synthetic_rows_and_nothing_else(db_session):
    from app.services.auth_service import auth_service

    real_user = auth_service.signup(db_session, "a-real-account@example.com", "correcthorse9!").user
    db_session.flush()

    generate(session=db_session)
    removed = reset(db_session)
    assert removed >= 50

    remaining_synthetic = db_session.query(User).filter(User.email.like(f"%{SYNTHETIC_EMAIL_SUFFIX}")).count()
    assert remaining_synthetic == 0
    assert db_session.get(User, real_user.id) is not None

    # No orphaned child rows left behind for any synthetic user.
    assert db_session.query(Subscription).count() == 0 or all(
        not s.user_id.startswith("synthetic") for s in db_session.query(Subscription).all()
    )


def test_reset_leaves_no_dangling_child_rows(db_session):
    generate(session=db_session)
    reset(db_session)
    remaining_users = {u.id for u in db_session.query(User).all()}
    for model in (Subscription, UsageEvent, UsagePeriod, RefreshToken):
        for row in db_session.query(model).all():
            assert row.user_id in remaining_users
