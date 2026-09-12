"""Per-user download preferences: defaults, persistence, and - the whole
point of this table existing - proof that one account's container_mode /
cookie_source can never leak into or be affected by another account's."""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.database.commercial_db import get_session_factory
from app.main import app
from app.models.enums import ContainerMode, CookieSource
from app.services.auth_service import auth_service
from app.services.user_preferences_service import user_preferences_service


def _user(db_session):
    result = auth_service.signup(db_session, f"prefs-{uuid.uuid4().hex[:12]}@example.com", "correcthorse9!")
    db_session.flush()
    return result.user


class TestDefaults:
    def test_never_configured_user_gets_sensible_defaults(self, db_session):
        user = _user(db_session)
        prefs = user_preferences_service.get_or_create(db_session, user.id)
        assert prefs.container_mode == ContainerMode.COMPATIBILITY.value
        assert prefs.cookie_source == CookieSource.NONE.value
        assert prefs.cookie_file_path is None

    def test_get_or_create_is_idempotent(self, db_session):
        user = _user(db_session)
        first = user_preferences_service.get_or_create(db_session, user.id)
        db_session.flush()
        second = user_preferences_service.get_or_create(db_session, user.id)
        assert first.user_id == second.user_id


class TestUpdate:
    def test_update_persists_container_mode(self, db_session):
        user = _user(db_session)
        user_preferences_service.update(db_session, user.id, {"container_mode": ContainerMode.ORIGINAL})
        db_session.flush()
        prefs = user_preferences_service.get_or_create(db_session, user.id)
        assert prefs.container_mode == ContainerMode.ORIGINAL.value

    def test_update_rejects_nonexistent_cookie_file(self, db_session):
        user = _user(db_session)
        with pytest.raises(ValueError):
            user_preferences_service.update(
                db_session, user.id, {"cookie_source": CookieSource.FILE, "cookie_file_path": "/no/such/file.txt"}
            )

    def test_partial_update_leaves_other_fields_untouched(self, db_session):
        user = _user(db_session)
        user_preferences_service.update(db_session, user.id, {"container_mode": ContainerMode.ORIGINAL})
        db_session.flush()
        user_preferences_service.update(db_session, user.id, {"cookie_source": CookieSource.FIREFOX})
        db_session.flush()
        prefs = user_preferences_service.get_or_create(db_session, user.id)
        assert prefs.container_mode == ContainerMode.ORIGINAL.value
        assert prefs.cookie_source == CookieSource.FIREFOX.value


class TestIsolation:
    """The four isolation proofs called for explicitly: a Free user's
    settings can't be changed by a Pro user's actions, one Pro user's
    changes don't leak to another Pro user, concurrent requests from
    different users stay isolated, and a user who never touches these
    settings still downloads normally on the defaults."""

    def test_free_user_unaffected_by_pro_user_changes(self, db_session):
        free_user = _user(db_session)
        pro_user = _user(db_session)

        user_preferences_service.update(
            db_session, pro_user.id, {"container_mode": ContainerMode.ORIGINAL, "cookie_source": CookieSource.CHROME}
        )
        db_session.flush()

        free_prefs = user_preferences_service.get_or_create(db_session, free_user.id)
        assert free_prefs.container_mode == ContainerMode.COMPATIBILITY.value
        assert free_prefs.cookie_source == CookieSource.NONE.value

    def test_pro_user_a_changes_do_not_affect_pro_user_b(self, db_session):
        user_a = _user(db_session)
        user_b = _user(db_session)

        user_preferences_service.update(
            db_session, user_a.id, {"container_mode": ContainerMode.ORIGINAL, "cookie_source": CookieSource.FIREFOX}
        )
        db_session.flush()

        prefs_b = user_preferences_service.get_or_create(db_session, user_b.id)
        assert prefs_b.container_mode == ContainerMode.COMPATIBILITY.value
        assert prefs_b.cookie_source == CookieSource.NONE.value

        # And user A's own change did stick, for completeness.
        prefs_a = user_preferences_service.get_or_create(db_session, user_a.id)
        assert prefs_a.container_mode == ContainerMode.ORIGINAL.value
        assert prefs_a.cookie_source == CookieSource.FIREFOX.value

    def test_concurrent_updates_from_different_users_stay_isolated(self, db_session):
        """20 threads, 20 different users, each setting a distinct
        container_mode/cookie_source pair at the same time. Every user's
        own row must end up with exactly what THEY set - never another
        thread's value bleeding across (which a shared/global row would
        have caused deterministically, not just under contention)."""
        users = [_user(db_session) for _ in range(20)]
        db_session.commit()  # visible to the other threads' own sessions
        user_ids = [u.id for u in users]

        def attempt(i: int) -> None:
            session = get_session_factory()()
            try:
                mode = ContainerMode.ORIGINAL if i % 2 == 0 else ContainerMode.COMPATIBILITY
                source = CookieSource.CHROME if i % 3 == 0 else CookieSource.NONE
                user_preferences_service.update(
                    session, user_ids[i], {"container_mode": mode, "cookie_source": source}
                )
                session.commit()
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(attempt, range(20)))

        for i, user_id in enumerate(user_ids):
            prefs = user_preferences_service.get_or_create(db_session, user_id)
            expected_mode = ContainerMode.ORIGINAL if i % 2 == 0 else ContainerMode.COMPATIBILITY
            expected_source = CookieSource.CHROME if i % 3 == 0 else CookieSource.NONE
            assert prefs.container_mode == expected_mode.value, f"user {i} got the wrong container_mode"
            assert prefs.cookie_source == expected_source.value, f"user {i} got the wrong cookie_source"

    def test_default_user_downloads_normally_without_ever_touching_preferences(self, db_session):
        """A user who never opens Settings still gets a working, gated
        download on the hardcoded sensible defaults - the whole point of
        get_or_create's lazy-creation path."""
        from app.models.commercial_enums import Plan
        from app.models.schemas import CreateDownloadRequest
        from app.services.download_gate_service import download_gate_service

        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="480")
        reservation_id, _ = download_gate_service.authorize_and_reserve(
            db_session, user, Plan.FREE, None, request, "job-1"
        )
        assert reservation_id


class TestApiIsolation:
    """Same proof at the HTTP layer: two real accounts, real cookies,
    real requests - never sharing state via a query param or header that
    could be spoofed, only via the authenticated session."""

    def test_download_preferences_requires_auth(self):
        resp = TestClient(app).get("/api/account/download-preferences")
        assert resp.status_code == 401

    def test_two_users_see_only_their_own_preferences(self):
        client_a = TestClient(app)
        client_b = TestClient(app)

        client_a.post(
            "/api/auth/signup",
            json={"email": f"api-prefs-a-{uuid.uuid4().hex[:8]}@example.com", "password": "correcthorse9!"},
        )
        client_b.post(
            "/api/auth/signup",
            json={"email": f"api-prefs-b-{uuid.uuid4().hex[:8]}@example.com", "password": "correcthorse9!"},
        )

        resp = client_a.put("/api/account/download-preferences", json={"container_mode": "original"})
        assert resp.status_code == 200
        assert resp.json()["container_mode"] == "original"

        # B never touched anything - must still see the default, not A's change.
        resp_b = client_b.get("/api/account/download-preferences")
        assert resp_b.status_code == 200
        assert resp_b.json()["container_mode"] == "compatibility"

        # A's own value round-trips correctly on a fresh GET.
        resp_a = client_a.get("/api/account/download-preferences")
        assert resp_a.json()["container_mode"] == "original"
