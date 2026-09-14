"""One-off helper for the browser E2E run: signs up (or reuses) a user and
grants them global super_admin, against whatever DATABASE_URL is
currently configured in the environment. Not part of the application -
purely an E2E test-setup utility."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database.db import get_session_factory  # noqa: E402
from app.database.models import User  # noqa: E402
from app.models.enums import GLOBAL_SCOPE, RoleSlug  # noqa: E402
from app.security.passwords import hash_password  # noqa: E402
from app.services import rbac_service  # noqa: E402

EMAIL = sys.argv[1] if len(sys.argv) > 1 else "e2e-super-admin@example.com"
PASSWORD = sys.argv[2] if len(sys.argv) > 2 else "correct-horse-battery"

session = get_session_factory()()
user = session.query(User).filter_by(email=EMAIL).first()
if user is None:
    user = User(email=EMAIL, password_hash=hash_password(PASSWORD), email_verified=True)
    session.add(user)
    session.flush()
rbac_service.assign_role(session, user, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE, granted_by=None)
session.commit()
print(f"OK: {EMAIL} is now a super_admin (id={user.id})")
