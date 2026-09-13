"""One-time data migration: encrypt any legacy plaintext
`platform_oidc_tokens` rows at rest (mission 4, phase 4).

Rows written before this mission stored `refresh_token`/`access_token` as
plaintext. Every write going forward (`platform_entitlement_service.
store_tokens`/`_refresh_access_token`) already stores an encrypted
envelope, so this script only matters for rows that predate that change
and haven't naturally been overwritten by a subsequent central sign-in.

Usage:
    python -m app.scripts.encrypt_platform_oidc_tokens

Safety properties:
- Idempotent: a row already in envelope form
  (`token_encryption_service.is_encrypted`) is left untouched, so running
  this repeatedly (or on a database with a mix of old and new rows) is
  safe.
- Never prints a token value, plaintext or ciphertext.
- Fails closed exactly like normal request handling: if no usable
  encryption key is configured for this environment, it exits non-zero
  without touching any row, rather than leaving some rows encrypted and
  others not.
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.database.commercial_db import get_session_factory
from app.database.commercial_models import PlatformOidcToken
from app.services import token_encryption_service


def encrypt_existing_rows() -> int:
    """Returns a process exit code: 0 on success (including "nothing to
    do"), 1 if encryption is unavailable in this environment."""
    try:
        # Touch the key loader once up front so a fail-closed environment
        # is caught before any row is (potentially partially) migrated.
        token_encryption_service.encrypt("startup-check")
    except token_encryption_service.TokenEncryptionUnavailableError as exc:
        print(f"Cannot run: {exc}")
        return 1

    session = get_session_factory()()
    try:
        rows = session.execute(select(PlatformOidcToken)).scalars().all()
        migrated = 0
        for row in rows:
            changed = False
            if not token_encryption_service.is_encrypted(row.refresh_token):
                row.refresh_token = token_encryption_service.encrypt(row.refresh_token)
                changed = True
            if row.access_token and not token_encryption_service.is_encrypted(row.access_token):
                row.access_token = token_encryption_service.encrypt(row.access_token)
                changed = True
            if changed:
                migrated += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"Checked {len(rows)} platform_oidc_tokens row(s); encrypted {migrated} legacy plaintext row(s).")
    return 0


if __name__ == "__main__":
    sys.exit(encrypt_existing_rows())
