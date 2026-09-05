"""app.scripts.promote_admin: existing-user-only, idempotent, no secrets."""
import uuid

from sqlalchemy import select

from app.database.commercial_db import get_session_factory
from app.database.commercial_models import User
from app.scripts.promote_admin import main, promote_admin
from app.services.auth_service import auth_service


def _make_user(db_session) -> User:
    result = auth_service.signup(db_session, f"promote-{uuid.uuid4().hex[:12]}@example.com", "correcthorse9!")
    db_session.commit()
    return result.user


class TestPromoteAdmin:
    def test_promotes_an_existing_user(self, db_session):
        user = _make_user(db_session)
        assert user.role == "user"

        exit_code = promote_admin(user.email)
        assert exit_code == 0

        refreshed = get_session_factory()().execute(select(User).where(User.id == user.id)).scalars().first()
        assert refreshed.role == "admin"

    def test_unknown_email_reports_not_found_and_creates_nothing(self, db_session, capsys):
        exit_code = promote_admin(f"nobody-{uuid.uuid4().hex[:12]}@example.com")
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "No user found" in out

    def test_idempotent_on_an_already_admin_user(self, db_session, capsys):
        user = _make_user(db_session)
        assert promote_admin(user.email) == 0
        capsys.readouterr()

        exit_code = promote_admin(user.email)
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "already an admin" in out

        refreshed = get_session_factory()().execute(select(User).where(User.id == user.id)).scalars().first()
        assert refreshed.role == "admin"

    def test_main_requires_exactly_one_argument(self):
        assert main([]) == 2
        assert main(["a@example.com", "extra"]) == 2

    def test_main_delegates_to_promote_admin(self, db_session):
        user = _make_user(db_session)
        assert main([user.email]) == 0
        refreshed = get_session_factory()().execute(select(User).where(User.id == user.id)).scalars().first()
        assert refreshed.role == "admin"
